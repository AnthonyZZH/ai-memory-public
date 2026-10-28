"""All conversation data is synthetic; fixtures are generated and retained."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import yaml
import zstandard

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conversation_processor import adapters, pipeline
from conversation_processor.common import candidate_id, now
from conversation_processor.config import load, local_endpoint
from conversation_processor.extract import Invalid, candidate, sensitive_guard, VALIDATOR, validate_unit, extract, PROMPT
from conversation_processor.store import Store
from conversation_processor.locking import acquire


def later():
    return (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()


def millis():
    return int((datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp() * 1000)


def fake_turn(session='fixture-session', ref='fixture:1', user='I prefer short answers.', assistant='I will be concise.'):
    return {'source': {'kind': 'sim', 'session': session, 'refs': [ref],
                       'source_time': later(), 'observed_at': now()},
            'persona_hash': '1234abcd', 'user': user, 'assistant': assistant}


def extracted(turn=None):
    return {'summary': 'Prefers short answers', 'quotes': [], 'category': 'preference',
            'importance': 2, 'sensitivity': 'normal', 'sensitivity_tags': [],
            'trait_signals': [], 'praise_only': False, 'expression': None}


@contextmanager
def fake_http(mode='valid'):
    state = {'mode': mode, 'calls': [], 'seen_system': []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['calls'].append(body)
            state['seen_system'].append(body['messages'][0]['content'])
            mode = state['mode']
            status = 503 if mode == 'unavailable' else 302 if mode == 'redirect' else 200
            self.send_response(status)
            if mode == 'redirect':
                self.send_header('Location', 'http://198.51.100.1/do-not-follow')
            self.end_headers()
            value = extracted()
            if mode == 'invalid':
                value['summary'] = 'x' * 41
            if mode == 'none':
                value['category'] = 'none'
            if mode in ('expression-repair', 'expression-invalid'):
                value['category'] = 'expression'
                value['expression'] = ({'text': 'I will be concise.'}
                    if mode == 'expression-invalid' or len(state['calls']) == 1 else 'I will be concise.')
            response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}
            self.wfile.write(json.dumps(response).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state['url'] = f'http://127.0.0.1:{server.server_port}/v1'
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class Cases(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get('PROCESSOR_TEST_ROOT', tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=base))
        self.data = self.root / 'data'
        self.data.mkdir()

    def config(self, source=None, url='http://127.0.0.1:1/v1'):
        source = source or {'id': 'fixture-source', 'kind': 'sim', 'path': 'data', 'pattern': '*.jsonl'}
        data = {'version': 1, 'cursor_db': 'state/cursors.sqlite', 'output_dir': 'out',
                'traits': ['fixture_trait'], 'sources': [source],
                'sensitivity': {'keyword_level': 'private', 'keywords': {'finance': ['bank balance']}},
                'extractor': {'base_url': url, 'model': 'fixture-local-model', 'timeout_seconds': 2,
                              'max_response_bytes': 65536, 'max_turn_chars': 2000,
                              'max_tokens': 512, 'temperature': 0.1}}
        path = self.root / 'processor.yaml'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        return load(path)

    def jsonl(self, path, records):
        path.write_bytes(b''.join((json.dumps(r, ensure_ascii=False) + '\n').encode() for r in records))

    def emitted(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in (self.root / 'out').glob('*.jsonl')]

    def test_sim_baseline_idempotent_outbox_recovery(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [fake_turn(ref='old')])
        with fake_http() as server:
            config = self.config(url=server['url'])
            self.assertEqual(pipeline.baseline(config)['extracted'], 0)
            self.assertEqual(pipeline.collect(config)['queued'], 0)
            self.jsonl(path, [fake_turn(ref='old'), fake_turn(ref='new')])
            self.assertEqual(pipeline.collect(config)['queued'], 1)
            self.assertEqual(pipeline.collect(config)['queued'], 0)
            self.assertEqual(pipeline.extract_pending(config)['emitted'], 1)
            self.assertEqual(pipeline.extract_pending(config)['emitted'], 0)
            self.assertEqual(len(server['calls']), 1)
            value = self.emitted()[0]
            self.assertTrue(VALIDATOR.is_valid(value))
            self.assertEqual(value['source']['refs'], ['new'])
            self.assertEqual(value['id'], candidate_id(fake_turn(ref='new')))
            db = sqlite3.connect(config.resolve(config.data['cursor_db']))
            db.execute('UPDATE outbox SET published=0')
            db.execute("UPDATE turns SET status='outbox'")
            db.commit()
            db.close()
            self.assertEqual(pipeline.extract_pending(config)['emitted'], 1)
            self.assertEqual(len(self.emitted()), 1)
            self.assertEqual(len(server['calls']), 1)
            self.assertEqual(set(server['calls'][0]), {'model', 'stream', 'temperature', 'max_tokens', 'messages'})
            self.assertEqual(len(server['calls'][0]['messages']), 2)

    def test_unavailable_retries_and_cursor_separation(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [])
        with fake_http('unavailable') as server:
            config = self.config(url=server['url'])
            pipeline.baseline(config)
            self.jsonl(path, [fake_turn()])
            pipeline.collect(config)
            self.assertEqual(pipeline.extract_pending(config)['pending'], 1)
            db = sqlite3.connect(config.resolve(config.data['cursor_db']))
            self.assertIsNone(db.execute('SELECT extracted_cursor FROM sessions').fetchone()[0])
            self.assertIn('line_offset', db.execute('SELECT read_cursor FROM sessions').fetchone()[0])
            db.close()
            server['mode'] = 'valid'
            self.assertEqual(pipeline.extract_pending(config)['emitted'], 1)
            self.assertEqual(len(self.emitted()), 1)

    def test_invalid_schema_dropped_without_body_logs(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [])
        with fake_http('invalid') as server:
            config = self.config(url=server['url'])
            pipeline.baseline(config)
            self.jsonl(path, [fake_turn(user='SYNTHETIC_PRIVATE_SENTINEL')])
            pipeline.collect(config)
            self.assertEqual(pipeline.extract_pending(config)['rejected'], 1)
            self.assertEqual(self.emitted(), [])
            db = sqlite3.connect(config.resolve(config.data['cursor_db']))
            events = str(db.execute('SELECT code,ref FROM events').fetchall())
            self.assertNotIn('SYNTHETIC_PRIVATE_SENTINEL', events)
            self.assertIsNone(db.execute('SELECT extracted_cursor FROM sessions').fetchone()[0])
            db.close()

    def test_none_not_output_and_redirect_not_followed(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [])
        with fake_http('none') as server:
            config = self.config(url=server['url'])
            pipeline.baseline(config)
            self.jsonl(path, [fake_turn(ref='first')])
            pipeline.collect(config)
            self.assertEqual(pipeline.extract_pending(config)['none'], 1)
            self.assertEqual(self.emitted(), [])
            server['mode'] = 'redirect'
            self.jsonl(path, [fake_turn(ref='first'), fake_turn(ref='second')])
            pipeline.collect(config)
            self.assertEqual(pipeline.extract_pending(config)['unavailable'], 1)
            self.assertEqual(len(server['calls']), 2)

    def test_loopback_only(self):
        for url in ['https://127.0.0.1/v1', 'http://192.0.2.1/v1', 'http://0.0.0.0/v1',
                    'http://localhost.evil/v1', 'http://user:pass@127.0.0.1/v1',
                    'http://127.0.0.1/v1?key=bad', 'http://[2001:db8::1]/v1']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_endpoint(url)
        self.assertEqual(local_endpoint('http://localhost:80/v1'), 'http://127.0.0.1:80/v1/chat/completions')

    def test_sensitive_guard_never_downgrades(self):
        config = self.config()
        turn = fake_turn(user='My bank balance is synthetic test data.')
        for level in ['normal', 'unsure', 'private']:
            value = candidate(turn, {**extracted(), 'sensitivity': level}, config)
            self.assertEqual(value['sensitivity'], 'private')
            self.assertIn('finance', value['sensitivity_tags'])
        config.data['sensitivity']['keyword_level'] = 'unsure'
        value = candidate(turn, {**extracted(), 'sensitivity': 'private'}, config)
        self.assertEqual(value['sensitivity'], 'private')
        value = candidate(fake_turn(), {**extracted(), 'sensitivity': 'unsure'}, config)
        self.assertEqual(value['sensitivity'], 'unsure')
        value = candidate(fake_turn(), {**extracted(), 'sensitivity_tags': ['health']}, config)
        self.assertEqual(value['sensitivity'], 'private')

    def praise_config(self):
        config = self.config()
        config.data['praise'] = {'keywords': ['adorable', 'love'],
                                'trait_aliases': {'fixture_trait': ['curious']}}
        return config

    def test_praise_plus_request_and_positive_trait_fallback(self):
        config = self.praise_config()
        payload = {**extracted(), 'trait_signals': [
            {'trait': 'fixture_trait', 'direction': 1, 'reason': 'synthetic'}]}
        for text in ('Your curious manner is adorable.', 'I love your curious manner, do more of it.'):
            self.assertTrue(candidate(fake_turn(user=text), payload, config)['praise_only'])
        self.assertFalse(payload['praise_only'])  # No caller mutation.

    def test_neutral_correction_and_other_trait_are_not_praise(self):
        config = self.praise_config()
        payload = {**extracted(), 'trait_signals': [
            {'trait': 'fixture_trait', 'direction': 1, 'reason': 'synthetic'}]}
        for text in ('Be less formal and more curious.', 'Your humor is adorable, do more of it.'):
            self.assertFalse(candidate(fake_turn(user=text), payload, config)['praise_only'])
        payload['trait_signals'][0]['direction'] = -1
        self.assertFalse(candidate(fake_turn(user='Your curious manner is adorable.'), payload, config)['praise_only'])

    def test_praise_flag_is_monotone_even_without_keywords(self):
        config = self.praise_config()
        payload = {**extracted(), 'praise_only': True}
        self.assertTrue(candidate(fake_turn(), payload, config)['praise_only'])
        config.data.pop('praise')
        self.assertTrue(candidate(fake_turn(), payload, config)['praise_only'])

    def test_expression_schema_retry_once_and_exact_grounding(self):
        with fake_http('expression-repair') as server:
            result = extract(fake_turn(), self.config(url=server['url']))
            self.assertEqual(result['expression'], 'I will be concise.')
            self.assertEqual(len(server['calls']), 2)
            retry = server['calls'][1]['messages'][-1]['content']
            self.assertIn('validator=type', retry)
            self.assertNotIn("{'text'", retry)
            self.assertEqual(len(server['calls'][0]['messages']), 2)

    def test_expression_invalid_after_retry_is_discarded(self):
        with fake_http('expression-invalid') as server:
            with self.assertRaisesRegex(Invalid, '^schema$'):
                extract(fake_turn(), self.config(url=server['url']))
            self.assertEqual(len(server['calls']), 2)

    def test_all_prompt_json_examples_pass_candidate_schema(self):
        examples = [json.loads(line) for line in PROMPT.splitlines() if line.startswith('{')]
        self.assertEqual(len(examples), 2)
        for payload in examples:
            turn = fake_turn(assistant='Let us call this a calendar traffic jam.')
            self.assertTrue(VALIDATOR.is_valid(candidate(turn, payload, self.config())))

    def test_group_markers_and_attack_words_block_expressions(self):
        config = self.config()
        config.data['expressions'] = {'non_owner_markers': ['group chat', 'third-party'],
                                      'aggressive_keywords': ['idiot']}
        payload = {**extracted(), 'category': 'expression', 'expression': 'Friendly saying'}
        for marker in ('This is group chat', 'From a third-party'):
            with self.assertRaisesRegex(Invalid, 'expression_scope'):
                candidate(fake_turn(user=marker, assistant='Friendly saying'), payload, config)
        for scope in ('group', 'third_party', 'unknown'):
            turn = fake_turn(assistant='Friendly saying')
            turn['source']['audience'] = scope
            with self.assertRaisesRegex(Invalid, 'expression_scope'):
                candidate(turn, payload, config)
        with self.assertRaisesRegex(Invalid, 'expression_scope'):
            candidate(fake_turn(assistant='An IDIOT!'), {**payload, 'expression':'An IDIOT!'}, config)
        self.assertEqual(candidate(fake_turn(assistant='Friendly saying'), payload, config)['category'], 'expression')

    def test_dsh_structured_audience_is_preserved(self):
        path = self.data / 'group.zstd'
        rows = self.dsh_round(0)
        rows[0]['data']['source']['audience'] = 'group'
        path.write_bytes(self.frame([self.dsh_header(agentPreset='fixture-persona'), *rows]))
        result = adapters.scan('dsh', path, self.dsh_source(), enabled_at=now())
        self.assertEqual(result.turns[0]['source']['audience'], 'group')

    def test_cc_structured_third_party_audience_is_preserved(self):
        path = self.data / 'third-party.jsonl'
        rows = [self.cc_snapshot(), self.cc_row('user', 'u', None, 'HUMAN', audience='third_party'),
                self.cc_row('assistant', 'a', 'u', [{'type': 'text', 'text': 'VISIBLE'}])]
        self.jsonl(path, rows)
        turns = adapters.scan('cc', path, self.cc_source(), enabled_at=now()).turns
        self.assertEqual(turns[0]['source']['audience'], 'third_party')

    def test_lm_structured_group_audience_is_preserved(self):
        path = self.data / 'group.conversation.json'
        data = {'createdAt': millis(), 'preset': '@local:fixture', 'chatType': 'group',
                'systemPrompt': '[persona sha256=1234abcd]', 'messages': [self.lm_user(),
                 {'versions': [self.lm_assistant('VISIBLE')], 'currentlySelected': 0}]}
        path.write_text(json.dumps(data), encoding='utf-8')
        turns = adapters.scan('lmstudio', path, self.lm_source(), enabled_at=now()).turns
        self.assertEqual(turns[0]['source']['audience'], 'group')

    def test_praise_config_invalid_rejected(self):
        config = self.config()
        for praise in ({'keywords': ['']}, {'trait_aliases': {'unknown': ['alias']}},
                       {'keywords': 'adorable'}, {'trait_aliases': {'fixture_trait': ['']}}):
            data = deepcopy(config.data)
            data['praise'] = praise
            config.path.write_text(yaml.safe_dump(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'invalid_praise_policy'):
                load(config.path)

    def test_quote_trait_and_expression_grounding(self):
        config = self.config()
        for change in [
            {'quotes': [{'speaker': 'owner', 'text': 'invented quotation'}]},
            {'trait_signals': [{'trait': 'not-configured', 'direction': 1, 'reason': 'test'}]},
            {'category': 'expression', 'expression': 'invented phrase'},
            {'source': {'bad': True}},
        ]:
            with self.subTest(change=change), self.assertRaises(Invalid):
                candidate(fake_turn(), {**extracted(), **change}, config)

    def dsh_source(self):
        return {'id': 'dsh-fixture', 'kind': 'dsh', 'path': 'data', 'pattern': '*.zstd',
                'preset': 'fixture-persona', 'persona_hash': '1234abcd'}

    def dsh_header(self, **extra):
        return {'type': 'session', 'version': 4, 'id': 'fixture-session',
                'agentPreset': 'standard', 'createdAt': millis(), **extra}

    def event(self, seq, typ, data):
        return {'seq': seq, 'time': millis(), 'type': typ, 'data': data}

    def frame(self, records):
        text = ''.join(json.dumps(r) + '\n' for r in records)
        return zstandard.ZstdCompressor(write_checksum=True).compress(text.encode())

    def large_window_frame(self, records):
        params = zstandard.ZstdCompressionParameters.from_level(
            3, window_log=27, enable_ldm=True, write_checksum=1)
        compressor = zstandard.ZstdCompressor(compression_params=params).compressobj()
        raw = ''.join(json.dumps(r) + '\n' for r in records).encode()
        return compressor.compress(raw) + compressor.flush()

    def test_dsh_large_window_multiframe_default_configured_and_incomplete_tail(self):
        from conversation_processor.adapters import dsh
        path = self.data / 'large.zstd'
        head = self.large_window_frame([self.dsh_header(agentPreset='fixture-persona')])
        tail = self.large_window_frame(self.dsh_round(0))
        self.assertEqual(zstandard.get_frame_parameters(head).window_size, 1 << 27)
        self.assertEqual(zstandard.get_frame_parameters(tail).window_size, 1 << 27)
        stats = {}
        rows, offset = dsh.frames(head + tail, statistics=stats)
        self.assertEqual((len(rows), offset, stats['frames']), (5, len(head + tail), 2))
        self.assertEqual(stats['max_declared_window_bytes'], 1 << 27)
        path.write_bytes(head + tail)
        source = self.dsh_source()
        self.assertEqual(len(adapters.scan('dsh', path, source, enabled_at=now()).turns), 1)
        source['max_window_size'] = 1 << 26
        with self.assertRaises(zstandard.ZstdError):
            adapters.scan('dsh', path, source, enabled_at=now())
        source['max_window_size'] = 1 << 27
        self.assertEqual(len(adapters.scan('dsh', path, source, enabled_at=now()).turns), 1)
        rows, offset = dsh.frames(head + tail[:-2], statistics=stats)
        self.assertEqual((len(rows), offset, stats['frames']), (1, len(head), 1))
        self.assertEqual(stats['incomplete_tail_bytes'], len(tail) - 2)
        source['max_file_bytes'] = len(head + tail) - 1
        with self.assertRaisesRegex(ValueError, 'source_too_large'):
            adapters.scan('dsh', path, source, enabled_at=now())

    def test_dsh_window_config_requires_bounded_byte_integer(self):
        from conversation_processor.adapters.dsh import frames
        for value in (0, 1023, True, '2147483648', (1 << 31) + 1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'invalid_max_window_size'):
                    self.config({**self.dsh_source(), 'max_window_size': value})
                with self.assertRaisesRegex(ValueError, 'invalid_max_window_size'):
                    frames(b'', max_window_size=value)

    def test_readonly_source_check_no_database_or_bodies(self):
        from check_sources import inspect
        self.jsonl(self.data / 'fixture.jsonl', [fake_turn(user='SYNTHETIC_BODY_DO_NOT_PRINT')])
        config = self.config()
        with patch('sqlite3.connect', side_effect=AssertionError('database access')):
            result = inspect(config)
        self.assertEqual(result['errors'], 0)
        self.assertEqual(result['sources'][0]['scanned'], 1)
        self.assertNotIn('SYNTHETIC_BODY_DO_NOT_PRINT', json.dumps(result))
        self.assertFalse(config.resolve(config.data['cursor_db']).exists())

    def dsh_round(self, start, turn=1, text='VISIBLE'):
        return [self.event(start, 'user/message', {'role': 'user', 'source': {'kind': 'user'}, 'content': [{'type': 'text', 'text': 'HUMAN'}]}),
                self.event(start + 1, 'turn/start', {'turn': turn}),
                self.event(start + 2, 'assistant/message', {'message': {'role': 'assistant', 'content': [{'type': 'reasoning', 'text': 'HIDDEN'}, {'type': 'text', 'text': text}]}}),
                self.event(start + 3, 'turn/end', {'turn': turn, 'reason': 'completed'})]

    def test_dsh_mid_preset_multiframe_incomplete_tail(self):
        path = self.data / 'session.zstd'
        source = self.dsh_source()
        header = self.dsh_header()
        path.write_bytes(self.frame([header]))
        config = self.config(source)
        pipeline.baseline(config)
        early = self.dsh_round(0)
        select = self.event(4, 'agent-preset/selected', {'agentPreset': 'fixture-persona'})
        normal = self.dsh_round(5, 2)
        prefix = self.frame([header]) + self.frame(early + [select] + normal[:2])
        tail = self.frame(normal[2:])
        path.write_bytes(prefix + tail[:-3])
        self.assertEqual(pipeline.collect(config)['queued'], 0)
        db = sqlite3.connect(config.resolve(config.data['cursor_db']))
        cursor = json.loads(db.execute('SELECT read_cursor FROM sessions').fetchone()[0])
        self.assertEqual(cursor['frame_offset'], len(prefix))
        db.close()
        path.write_bytes(prefix + tail)
        self.assertEqual(pipeline.collect(config)['queued'], 1)
        self.assertEqual(pipeline.collect(config)['queued'], 0)
        store = Store(config.resolve(config.data['cursor_db']))
        value = json.loads(store.db.execute('SELECT unit_json FROM turns').fetchone()[0])
        store.close()
        self.assertEqual(value['assistant'], 'VISIBLE')
        self.assertEqual(value['source']['refs'][0], 'seq:5')
        self.assertNotIn('HIDDEN', json.dumps(value))

    def test_dsh_baseline_skips_old_pending_turn_and_synthetic_user(self):
        path = self.data / 'session.zstd'
        source = self.dsh_source()
        header = self.dsh_header(agentPreset='fixture-persona')
        first = self.dsh_round(0)
        path.write_bytes(self.frame([header, *first[:2]]))
        config = self.config(source)
        pipeline.baseline(config)
        synthetic = self.event(4, 'user/message', {'source': {'kind': 'runtime-context'}, 'content': [{'type': 'text', 'text': 'NOT HUMAN'}]})
        path.write_bytes(self.frame([header, *first, synthetic]))
        self.assertEqual(pipeline.collect(config)['queued'], 0)
        with self.assertRaises(ValueError):
            pipeline.baseline(config)

    def test_dsh_seed_prefix_excluded(self):
        path = self.data / 'session.zstd'
        header = self.dsh_header(agentPreset='fixture-persona', isSeeded=True, seedLength=4)
        path.write_bytes(self.frame([header, *self.dsh_round(0), *self.dsh_round(4, 2)]))
        result = adapters.scan('dsh', path, self.dsh_source(), enabled_at=now())
        self.assertEqual(len(result.turns), 1)
        self.assertEqual(result.turns[0]['source']['refs'][0], 'seq:4')

    def lm_source(self):
        return {'id': 'lm-fixture', 'kind': 'lmstudio', 'path': 'data', 'pattern': '*.conversation.json',
                'presets': ['@local:fixture'], 'require_persona_marker': True}

    def lm_user(self, text='HUMAN'):
        return {'versions': [{'type': 'singleStep', 'role': 'user', 'content': [{'type': 'text', 'text': text}]}], 'currentlySelected': 0}

    def lm_assistant(self, text, ready=True):
        step = {'type': 'contentBlock', 'stepIdentifier': 'text-' + text, 'content': [{'type': 'text', 'text': text}]}
        if ready:
            step['genInfo'] = {'stats': {'totalTimeSec': 1}}
        return {'type': 'multiStep', 'role': 'assistant', 'steps': [
            {'type': 'contentBlock', 'style': {'type': 'thinking', 'ended': True}, 'content': [{'type': 'text', 'text': 'HIDDEN'}]},
            {'type': 'contentBlock', 'roleOverride': 'tool', 'content': [{'type': 'text', 'text': 'TOOL SECRET'}]},
            {'type': 'contentBlock', 'content': [{'type': 'toolCallResult', 'result': 'TOOL SECRET'}]},
            {'type': 'debugInfoBlock', 'debugInfo': 'DEBUG'}, step]}

    def test_lm_selected_version_thinking_and_switch_idempotent(self):
        path = self.data / 'fixture.conversation.json'
        doc = {'createdAt': millis(), 'preset': '@local:fixture', 'systemPrompt': '[persona sha256=1234abcd]', 'messages': []}
        path.write_text(json.dumps(doc), encoding='utf-8')
        config = self.config(self.lm_source())
        pipeline.baseline(config)
        doc['messages'] = [self.lm_user(), {'versions': [self.lm_assistant('OLD'), self.lm_assistant('CURRENT')], 'currentlySelected': 1}]
        path.write_text(json.dumps(doc), encoding='utf-8')
        self.assertEqual(pipeline.collect(config)['queued'], 1)
        doc['messages'][1]['currentlySelected'] = 0
        path.write_text(json.dumps(doc), encoding='utf-8')
        self.assertEqual(pipeline.collect(config)['queued'], 0)
        store = Store(config.resolve(config.data['cursor_db']))
        turn = json.loads(store.db.execute('SELECT unit_json FROM turns').fetchone()[0])
        store.close()
        self.assertEqual(turn['assistant'], 'CURRENT')
        self.assertIsNone(turn['source']['source_time'])

    def test_lm_pending_completion_and_old_turn_baseline(self):
        path = self.data / 'fixture.conversation.json'
        source = self.lm_source()
        doc = {'createdAt': millis(), 'preset': '@local:fixture', 'systemPrompt': '[persona sha256=1234abcd]', 'messages': [self.lm_user()]}
        path.write_text(json.dumps(doc), encoding='utf-8')
        initial = adapters.scan('lmstudio', path, source, baseline=True, enabled_at=now())
        doc['messages'].append({'versions': [self.lm_assistant('OLD LATE')], 'currentlySelected': 0})
        doc['messages'] += [self.lm_user('NEW'), {'versions': [self.lm_assistant('PARTIAL', False)], 'currentlySelected': 0}]
        path.write_text(json.dumps(doc), encoding='utf-8')
        pending = adapters.scan('lmstudio', path, source, initial.cursor, enabled_at=now())
        self.assertEqual(pending.turns, [])
        doc['messages'][3]['versions'][0] = self.lm_assistant('DONE')
        path.write_text(json.dumps(doc), encoding='utf-8')
        ready = adapters.scan('lmstudio', path, source, pending.cursor, enabled_at=now())
        self.assertEqual(len(ready.turns), 1)
        self.assertEqual(ready.turns[0]['assistant'], 'DONE')

    def cc_source(self):
        return {'id': 'cc-fixture', 'kind': 'cc', 'path': 'data', 'pattern': '*.jsonl',
                'cwd': 'Z:/fixture/workspace', 'models': ['fixture-local-model']}

    def cc_row(self, typ, uuid, parent, content, model='fixture-local-model', message_id='a1', **extra):
        message = {'role': typ, 'content': content}
        if typ == 'assistant':
            message.update(id=message_id, model=model, stop_reason='end_turn')
        return {'type': typ, 'uuid': uuid, 'parentUuid': parent, 'sessionId': 'fixture-session',
                'timestamp': later(), 'cwd': self.cc_source()['cwd'], 'message': message, **extra}

    def cc_snapshot(self):
        return {'type': 'attachment', 'sessionId': 'fixture-session',
                'attachment': {'type': 'prompt_snapshot', 'systemPrompt': ['[persona sha256=1234abcd]']}}

    def test_cc_fragments_tool_result_and_other_model(self):
        path = self.data / 'fixture.jsonl'
        self.jsonl(path, [])
        config = self.config(self.cc_source())
        pipeline.baseline(config)
        rows = [self.cc_snapshot(), self.cc_row('user', 'u1', None, 'HUMAN', turnOrigin='human'),
                self.cc_row('assistant', 'a-think', 'u1', [{'type': 'thinking', 'thinking': 'HIDDEN'}]),
                self.cc_row('user', 'tool-result', 'a-think', [{'type': 'tool_result', 'content': 'FAKE HUMAN'}]),
                self.cc_row('assistant', 'a-text', 'tool-result', [{'type': 'text', 'text': 'VISIBLE'}]),
                self.cc_row('user', 'u2', 'a-text', 'SECOND HUMAN'),
                self.cc_row('assistant', 'other', 'u2', [{'type': 'text', 'text': 'OTHER MODEL'}], model='other-model', message_id='a2')]
        self.jsonl(path, rows)
        self.assertEqual(pipeline.collect(config)['queued'], 1)
        self.assertEqual(pipeline.collect(config)['queued'], 0)
        store = Store(config.resolve(config.data['cursor_db']))
        turn = json.loads(store.db.execute('SELECT unit_json FROM turns').fetchone()[0])
        store.close()
        self.assertEqual(turn['user'], 'HUMAN')
        self.assertEqual(turn['assistant'], 'VISIBLE')
        self.assertNotIn('HIDDEN', json.dumps(turn))

    def test_cc_current_parent_branch_and_marker_required(self):
        path = self.data / 'fixture.jsonl'
        rows = [self.cc_snapshot(), self.cc_row('user', 'u', None, 'HUMAN'),
                self.cc_row('assistant', 'orphan', 'u', [{'type': 'text', 'text': 'ORPHAN'}], message_id='old'),
                self.cc_row('assistant', 'current', 'u', [{'type': 'text', 'text': 'CURRENT'}], message_id='new')]
        self.jsonl(path, rows)
        result = adapters.scan('cc', path, self.cc_source(), enabled_at=now())
        self.assertEqual(len(result.turns), 1)
        self.assertEqual(result.turns[0]['assistant'], 'CURRENT')
        self.jsonl(path, rows[1:])
        self.assertEqual(adapters.scan('cc', path, self.cc_source(), enabled_at=now()).turns, [])

    def test_cc_baseline_and_incomplete_tail(self):
        path = self.data / 'fixture.jsonl'
        rows = [self.cc_snapshot(), self.cc_row('user', 'u', None, 'OLD HUMAN')]
        self.jsonl(path, rows)
        initial = adapters.scan('cc', path, self.cc_source(), baseline=True, enabled_at=now())
        rows.append(self.cc_row('assistant', 'a', 'u', [{'type': 'text', 'text': 'OLD LATE'}]))
        self.jsonl(path, rows)
        with path.open('ab') as stream:
            stream.write(b'{"incomplete":')
        result = adapters.scan('cc', path, self.cc_source(), initial.cursor, enabled_at=now())
        self.assertEqual(result.turns, [])
        self.assertEqual(result.cursor['line_offset'], initial.cursor['line_offset'] + len((json.dumps(rows[-1]) + '\n').encode()))

    def test_collect_requires_explicit_baseline(self):
        self.jsonl(self.data / 'turns.jsonl', [fake_turn()])
        config = self.config()
        with self.assertRaises(ValueError):
            pipeline.collect(config)
        self.assertEqual(self.emitted(), [])

    def test_concurrent_worker_refused_without_stale_lock(self):
        path = self.data / 'fixture.jsonl'
        self.jsonl(path, [])
        config = self.config()
        pipeline.baseline(config)
        lock = config.resolve(config.data['cursor_db']).with_suffix('.mutex')
        with acquire(lock):
            with self.assertRaises(ValueError):
                pipeline.collect(config)
        self.assertEqual(pipeline.collect(config)['queued'], 0)
        self.assertTrue(lock.exists())

    def test_dsh_partial_frame_at_baseline_is_old_even_if_completed_later(self):
        path = self.data / 'fixture.zstd'
        source = self.dsh_source()
        header = self.dsh_header(agentPreset='fixture-persona')
        old = self.frame(self.dsh_round(0))
        head = self.frame([header])
        path.write_bytes(head + old[:-3])
        initial = adapters.scan('dsh', path, source, baseline=True, enabled_at=now())
        path.write_bytes(head + old + self.frame(self.dsh_round(4, 2, 'NEW')))
        result = adapters.scan('dsh', path, source, initial.cursor, enabled_at=now())
        self.assertEqual(len(result.turns), 1)
        self.assertEqual(result.turns[0]['assistant'], 'NEW')

    def test_sim_partial_line_at_baseline_skipped(self):
        path = self.data / 'fixture.jsonl'
        source = {'id': 'sim', 'kind': 'sim', 'path': 'data', 'pattern': '*.jsonl'}
        raw = (json.dumps(fake_turn(ref='old')) + '\n').encode()
        path.write_bytes(raw[:20])
        initial = adapters.scan('sim', path, source, baseline=True, enabled_at=now())
        path.write_bytes(raw + (json.dumps(fake_turn(ref='new')) + '\n').encode())
        result = adapters.scan('sim', path, source, initial.cursor, enabled_at=now())
        self.assertEqual(len(result.turns), 1)
        self.assertEqual(result.turns[0]['source']['refs'], ['new'])

    def test_lm_switching_into_eligible_preset_does_not_backfill(self):
        path = self.data / 'fixture.conversation.json'
        source = self.lm_source()
        doc = {'createdAt': millis(), 'preset': '@local:other', 'systemPrompt': '[persona sha256=1234abcd]',
               'messages': [self.lm_user(), {'versions': [self.lm_assistant('INELIGIBLE')], 'currentlySelected': 0}]}
        path.write_text(json.dumps(doc), encoding='utf-8')
        skipped = adapters.scan('lmstudio', path, source, enabled_at=now())
        doc['preset'] = '@local:fixture'
        path.write_text(json.dumps(doc), encoding='utf-8')
        result = adapters.scan('lmstudio', path, source, skipped.cursor, enabled_at=now())
        self.assertEqual(result.turns, [])

    def test_cc_partial_human_line_at_baseline_skipped(self):
        path = self.data / 'fixture.jsonl'
        head = (json.dumps(self.cc_snapshot()) + '\n').encode()
        old_user = (json.dumps(self.cc_row('user', 'u1', None, 'OLD')) + '\n').encode()
        path.write_bytes(head + old_user[:20])
        initial = adapters.scan('cc', path, self.cc_source(), baseline=True, enabled_at=now())
        end = self.cc_row('assistant', 'a1', 'u1', [{'type': 'text', 'text': 'OLD LATE'}])
        path.write_bytes(head + old_user + (json.dumps(end) + '\n').encode())
        self.assertEqual(adapters.scan('cc', path, self.cc_source(), initial.cursor, enabled_at=now()).turns, [])

    def test_cc_late_duplicate_message_fragment_does_not_duplicate_candidate(self):
        path = self.data / 'fixture.jsonl'
        self.jsonl(path, [])
        config = self.config(self.cc_source())
        pipeline.baseline(config)
        rows = [self.cc_snapshot(), self.cc_row('user', 'u1', None, 'HUMAN'),
                self.cc_row('assistant', 'a1', 'u1', [{'type': 'text', 'text': 'FINAL'}])]
        self.jsonl(path, rows)
        self.assertEqual(pipeline.collect(config)['queued'], 1)
        rows.append(self.cc_row('assistant', 'a2', 'a1', [{'type': 'text', 'text': 'FINAL'}]))
        self.jsonl(path, rows)
        self.assertEqual(pipeline.collect(config)['queued'], 0)

    def test_bad_timestamps_rejected_without_optional_format_dependencies(self):
        turn = fake_turn()
        turn['source']['observed_at'] = 'not-a-time'
        with self.assertRaises(Invalid):
            validate_unit(turn)
        turn = fake_turn()
        turn['source']['source_time'] = '2026-01-01T12:00:00'
        with self.assertRaises(Invalid):
            validate_unit(turn)

    def test_disabled_source_queue_is_not_extracted(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [])
        with fake_http() as server:
            config = self.config(url=server['url'])
            pipeline.baseline(config)
            self.jsonl(path, [fake_turn()])
            pipeline.collect(config)
            config.data['sources'][0]['enabled'] = False
            self.assertEqual(pipeline.extract_pending(config)['emitted'], 0)
            self.assertEqual(server['calls'], [])

    def test_output_conflict_never_overwrites_existing_file(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [])
        with fake_http() as server:
            config = self.config(url=server['url'])
            pipeline.baseline(config)
            turn = fake_turn()
            self.jsonl(path, [turn])
            pipeline.collect(config)
            output = self.root / 'out'
            output.mkdir()
            target = output / (candidate_id(turn) + '.jsonl')
            target.write_bytes(b'preserved conflict fixture\n')
            self.assertEqual(pipeline.extract_pending(config)['pending'], 1)
            self.assertEqual(target.read_bytes(), b'preserved conflict fixture\n')
            self.assertEqual(len(server['calls']), 1)

    def test_lm_protocol_allows_preset_without_hash(self):
        source = self.lm_source()
        source['require_persona_marker'] = False
        path = self.data / 'fixture.conversation.json'
        doc = {'createdAt': millis(), 'preset': '@local:fixture', 'systemPrompt': '',
               'messages': [self.lm_user(), {'versions': [self.lm_assistant('FINAL')], 'currentlySelected': 0}]}
        path.write_text(json.dumps(doc), encoding='utf-8')
        result = adapters.scan('lmstudio', path, source, enabled_at=now())
        self.assertEqual(len(result.turns), 1)
        self.assertIsNone(result.turns[0]['persona_hash'])

    def test_loader_marker_formats_and_invalid_suffix(self):
        from conversation_processor.markers import hashes
        self.assertEqual(hashes('[persona sha256=abcdef12] [persona sha256=9876abcd 字数=123]', {}), ['abcdef12', '9876abcd'])
        for invalid in ('[persona sha256=abcdef123]', '[persona sha256=abcdef12evil]', '[persona sha256=abcdef12', '[persona sha256=NOTAHASH]'):
            self.assertEqual(hashes(invalid, {}), [])

    def test_dsh_evolving_hashes_are_provenance_not_filters(self):
        source = self.dsh_source()
        source.pop('persona_hash')
        path = self.data / 'evolving.zstd'
        header = self.dsh_header(agentPreset='fixture-persona')
        rows = [header, self.event(0, 'request/context', {'systemPromptUpdate': '[persona sha256=aaaaaaaa 字数=100]'}),
                *self.dsh_round(1), self.event(5, 'request/context', {'systemPromptUpdate': '[persona sha256=bbbbbbbb 字数=101]'}),
                *self.dsh_round(6, 2)]
        path.write_bytes(self.frame(rows))
        result = adapters.scan('dsh', path, source, enabled_at=now())
        self.assertEqual([r['persona_hash'] for r in result.turns], ['aaaaaaaa', 'bbbbbbbb'])

    def test_cc_evolving_hashes_do_not_disable_rounds(self):
        path = self.data / 'evolving.jsonl'
        first, second = self.cc_snapshot(), self.cc_snapshot()
        first['attachment']['systemPrompt'] = ['[persona sha256=aaaaaaaa 字数=100]']
        second['attachment']['systemPrompt'] = ['[persona sha256=bbbbbbbb 字数=101]']
        rows = [first, self.cc_row('user', 'u1', None, 'ONE'),
                self.cc_row('assistant', 'a1', 'u1', 'ANSWER ONE', message_id='m1'),
                self.cc_row('user', 'u2', 'a1', 'TWO'), second,
                self.cc_row('assistant', 'a2', 'u2', 'ANSWER TWO', message_id='m2')]
        self.jsonl(path, rows)
        result = adapters.scan('cc', path, self.cc_source(), enabled_at=now())
        self.assertEqual([r['persona_hash'] for r in result.turns], ['aaaaaaaa', 'bbbbbbbb'])

    def test_cli_baseline_run_and_status_with_fake_http(self):
        path = self.data / 'turns.jsonl'
        self.jsonl(path, [fake_turn(ref='old')])
        entry = Path(__file__).resolve().parents[1] / 'processor.py'
        with fake_http() as server:
            config = self.config(url=server['url'])
            prefix = [sys.executable, '-B', '-X', 'utf8', str(entry), '--config', str(config.path)]
            first = subprocess.run([*prefix, 'baseline', '--confirm'], capture_output=True, text=True,
                                   encoding='utf-8', timeout=15)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(json.loads(first.stdout)['extracted'], 0)
            self.jsonl(path, [fake_turn(ref='old'), fake_turn(ref='new')])
            run = subprocess.run([*prefix, 'run', '--limit', '1'], capture_output=True, text=True,
                                 encoding='utf-8', timeout=15)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(json.loads(run.stdout)['extract']['emitted'], 1)
            status = subprocess.run([*prefix, 'status'], capture_output=True, text=True,
                                    encoding='utf-8', timeout=15)
            self.assertEqual(json.loads(status.stdout)['turns'], {'emitted': 1})
            self.assertEqual(len(server['calls']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
