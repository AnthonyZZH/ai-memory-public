"""Synthetic data only. Runtime git writes are confined to retained temp repos."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'conversation-processor')]
from personality_engine import engine, gitops
from personality_engine.policy import Config, EngineError, canonical, digest, exclusive, now
from personality_engine.store import Store
from conversation_processor.common import candidate_id
from conversation_processor import pipeline
from conversation_processor.config import load as processor_load


def approve_reviews(body, reason='Grounded correction.', decision='approve'):
    candidates = json.loads(body['messages'][1]['content'])['candidates']
    return {'reviews': [{'id': c['id'], 'decision': decision, 'reason': reason} for c in candidates]}


class FakeHTTP:
    def __init__(self, content):
        self.requests = []
        self.content = content
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.requests.append(body)
                payload = outer.content(body) if callable(outer.content) else outer.content
                data = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(payload)}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port) + '/v1'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class Fixture:
    def __init__(self):
        base = Path(os.environ.get('ENGINE_TEST_ROOT', 'E:/Codex Development/tmp/v2.2b/tests'))
        base.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix='engine-', dir=base))
        self.root, self.private = self.folder / 'main', self.folder / 'private'
        self.cfg = self.folder / 'engine.yaml'
        self.proc_cfg = self.folder / 'processor.yaml'
        self.output = self.folder / 'candidates'
        self.output.mkdir()
        self.lock = {'version': 1, 'evolution': {
            'max_step_per_trait': 3, 'monthly_drift_needs_approval': 10,
            'min_evidence_episodes': 3, 'min_evidence_sessions': 2, 'drift_window_days': 30,
            'must_stay_in_range': True, 'forbid_sycophancy': True,
            'locked_files': ['her/persona.md', 'her/voice.md', 'her/identity-lock.yaml'],
            'writable_by_engine': ['her/episodes/', 'her/evolution/', 'her/personality.json', 'her/relationship.md']}}
        for repo in (self.root, self.private):
            (repo / 'her').mkdir(parents=True)
            (repo / '.gitignore').write_text('cache/\n', encoding='utf-8')
        (self.root / 'her/identity-lock.yaml').write_text(yaml.safe_dump(self.lock), encoding='utf-8')
        (self.root / 'her/persona.md').write_text('owner-only persona\n', encoding='utf-8')
        (self.root / 'her/voice.md').write_text('owner-only voice\n', encoding='utf-8')
        self.personality = {'version': 1, 'traits': {'curiosity': {'value': 50, 'range': [40, 60], 'basis': 'synthetic'}}}
        (self.root / 'her/personality.json').write_text(json.dumps(self.personality, indent=2) + '\n', encoding='utf-8')
        self.data = {'version': 1, 'repository': str(self.root), 'private_repository': str(self.private),
                     'processor_config': str(self.proc_cfg), 'reflect_every': 20, 'expression_limit': 30,
                     'max_candidate_bytes': 1048576, 'max_reflection_episodes': 100,
                     'git_identity': {'name': 'Synthetic Engine', 'email': 'synthetic@localhost'},
                     'reflector': {'base_url': 'http://127.0.0.1:1/v1', 'model': 'synthetic', 'timeout_seconds': 1,
                                   'temperature': 0.1, 'max_tokens': 2048, 'max_response_bytes': 1048576,
                                   'max_input_chars': 48000}}
        self.proc = {'version': 1, 'cursor_db': str(self.folder / 'processor/cursors.sqlite'), 'output_dir': str(self.output),
                     'traits': ['curiosity'], 'sources': [],
                     'extractor': {'base_url': 'http://127.0.0.1:1/v1', 'model': 'synthetic', 'timeout_seconds': 1,
                                   'temperature': 0.1, 'max_tokens': 2048, 'max_response_bytes': 1048576, 'max_turn_chars': 32000},
                     'sensitivity': {'keyword_level': 'private', 'keywords': {'finance': ['secret-balance']}}}
        self.save()
        self.config = Config(self.cfg)
        # These fixture repos are initialized by the same runtime git wrapper;
        # no production repository is modified by tests.
        for repo in (self.root, self.private):
            gitops.git(self.config, repo, 'init')
            gitops.git(self.config, repo, 'add', '--', '.gitignore', 'her') if repo == self.root else gitops.git(self.config, repo, 'add', '--', '.gitignore')
            gitops.git(self.config, repo, 'commit', '-m', 'synthetic baseline')
        self.store = Store(self.config)

    def save(self):
        self.cfg.write_text(yaml.safe_dump(self.data), encoding='utf-8')
        self.proc_cfg.write_text(yaml.safe_dump(self.proc), encoding='utf-8')

    def reload(self):
        self.save()
        self.config = Config(self.cfg)

    def candidate(self, number=1, **overrides):
        value = {'schema': 'memory-candidate/v1', 'id': '',
                 'source': {'kind': 'sim', 'session': 'session-' + str(number % 2), 'refs': ['turn:' + str(number)],
                            'source_time': None, 'observed_at': '2026-10-28T00:00:00+00:00'},
                 'persona_hash': '12345678', 'summary': 'Corrections support investigation.',
                 'quotes': [], 'category': 'correction', 'importance': 3, 'sensitivity': 'normal',
                 'sensitivity_tags': [], 'trait_signals': [{'trait': 'curiosity', 'direction': 1, 'reason': 'verified correction'}],
                 'praise_only': False, 'expression': None}
        value.update(overrides)
        value['id'] = candidate_id(value)
        return value

    def emit(self, value):
        (self.output / (value['id'] + '.jsonl')).write_text(canonical(value) + '\n', encoding='utf-8')
        return value['id']

    def seed(self, count=3, **overrides):
        ids = []
        for i in range(count):
            value = self.candidate(i, **overrides)
            ids.append(value['id'])
            self.emit(value)
        engine.consume(self.config, self.store)
        return ids

    def proposal(self, evidence=None, **overrides):
        value = {'trait': 'curiosity', 'delta': 1, 'evidence': evidence or self.seed(),
                 'counter_evidence': [], 'reason': 'Several independent corrections support curiosity.'}
        value.update(overrides)
        return value

    def ready(self, raw):
        value = engine.guard(self.config, self.store, {**raw, 'id': digest(raw)[:16], 'created_at': now()})
        engine.store_proposal(self.config, self.store, value)
        return value

    def value(self):
        return json.loads((self.root / 'her/personality.json').read_text(encoding='utf-8'))['traits']['curiosity']['value']

    def close(self):
        self.store.close()


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_normal_note_and_idempotent_consumption(self):
        value = self.f.candidate()
        self.f.emit(value)
        first = engine.consume(self.f.config, self.f.store)
        sha = gitops.head(self.f.config, self.f.root)
        second = engine.consume(self.f.config, self.f.store)
        self.assertEqual((first['normal'], second['duplicate']), (1, 1))
        self.assertEqual(sha, gitops.head(self.f.config, self.f.root))
        path = self.f.root / ('her/episodes/2026-10/' + value['id'] + '.md')
        text = path.read_text(encoding='utf-8')
        metadata = yaml.safe_load(text.split('---')[1])
        self.assertEqual(metadata['visibility'], 'her')
        self.assertIn('## Observations', text)
        self.assertIn('## Relations', text)

    def test_private_unsure_categories_never_public(self):
        original = {str(p.relative_to(self.f.root)): p.read_bytes() for p in (self.f.root / 'her').rglob('*') if p.is_file()}
        for index, (sensitivity, category) in enumerate([('private', 'relationship'), ('unsure', 'expression')]):
            value = self.f.candidate(index, sensitivity=sensitivity, category=category,
                                     summary='PRIVATE-SYNTHETIC-TITLE', expression='PRIVATE-SYNTHETIC-EXPRESSION' if category == 'expression' else None)
            self.f.emit(value)
        result = engine.consume(self.f.config, self.f.store)
        self.assertEqual(result['private'], 2)
        current = {str(p.relative_to(self.f.root)): p.read_bytes() for p in (self.f.root / 'her').rglob('*') if p.is_file()}
        self.assertEqual(original, current)
        self.assertEqual(len(list((self.f.private / 'her/episodes').rglob('*.md'))), 2)
        for path in (self.f.private / 'her/episodes').rglob('*.md'):
            self.assertIn('visibility: private', path.read_text(encoding='utf-8'))
        self.assertTrue(all(r[0] is None for r in self.f.store.db.execute('SELECT payload FROM consumed')))
        main_cache = b''.join(p.read_bytes() for p in self.f.config.cache.rglob('*') if p.is_file())
        self.assertNotIn(b'PRIVATE-SYNTHETIC', main_cache)
        self.assertIn(b'xq-memory:', gitops.git(self.f.config, self.f.private, 'log', '--oneline').stdout)

    def test_sensitivity_tags_and_keywords_only_increase(self):
        self.f.emit(self.f.candidate(1, sensitivity_tags=['finance']))
        self.f.emit(self.f.candidate(2, summary='secret-balance synthetic'))
        self.assertEqual(engine.consume(self.f.config, self.f.store)['private'], 2)
        self.assertFalse((self.f.root / 'her/episodes').exists())

    def test_top_level_only_and_schema_validation(self):
        nested = self.f.output / 'staging'
        nested.mkdir()
        (nested / 'candidate.jsonl').write_text(canonical(self.f.candidate()), encoding='utf-8')
        (self.f.output / 'bad.jsonl').write_text('{bad\n' + canonical({'schema': 'invalid'}) + '\n', encoding='utf-8')
        result = engine.consume(self.f.config, self.f.store)
        self.assertEqual((result['consumed'], result['invalid']), (0, 2))

    def test_candidate_id_conflict_fails_closed(self):
        value = self.f.candidate()
        self.f.emit(value)
        engine.consume(self.f.config, self.f.store)
        value['summary'] = 'A different conclusion.'
        self.f.emit(value)
        with self.assertRaisesRegex(EngineError, 'candidate_id_conflict'):
            engine.consume(self.f.config, self.f.store)

    def test_forged_id_rejected(self):
        value = self.f.candidate()
        value['id'] = '0' * 16
        self.f.emit(value)
        self.assertEqual(engine.consume(self.f.config, self.f.store)['invalid'], 1)

    def test_relationship_summary_append_once(self):
        value = self.f.candidate(category='relationship')
        self.f.emit(value)
        engine.consume(self.f.config, self.f.store)
        engine.consume(self.f.config, self.f.store)
        text = (self.f.root / 'her/relationship.md').read_text(encoding='utf-8')
        self.assertEqual(text.count(value['summary']), 1)

    def test_relationship_missing_grant_fails_without_writes(self):
        self.f.config.rules['writable_by_engine'].remove('her/relationship.md')
        # Policy-current validation remains anchored in the disk policy.
        self.f.emit(self.f.candidate(category='relationship'))
        with self.assertRaisesRegex(EngineError, 'write_not_whitelisted'):
            engine.consume(self.f.config, self.f.store)
        self.assertFalse((self.f.root / 'her/episodes').exists())

    def test_expression_dedup_and_lru_limit(self):
        # No need for 32 git commits: validate the expression registry algorithm
        # directly, then verify the complete route in a separate test.
        for i in range(31):
            value = self.f.candidate(i, category='expression', expression='expression-' + str(i))
            value['source']['observed_at'] = '2026-10-28T00:' + format(i, '02d') + ':00+00:00'
            output = engine.expression_changes(self.f.config, value)
            self.f.config.write(self.f.root / 'her/evolution/expressions.md', output)
        value = self.f.candidate(32, category='expression', expression='expression-1')
        value['source']['observed_at'] = '2026-10-28T01:00:00+00:00'
        output = engine.expression_changes(self.f.config, value)
        entries = yaml.safe_load(output.split('---')[1])['entries']
        self.assertEqual(len(entries), 30)
        self.assertNotIn('expression-0', [e['text'] for e in entries])
        self.assertEqual(entries[0]['text'], 'expression-1')

    def test_expression_route_writes_episode_and_registry(self):
        self.f.emit(self.f.candidate(category='expression', expression='A synthetic expression.'))
        engine.consume(self.f.config, self.f.store)
        self.assertTrue((self.f.root / 'her/evolution/expressions.md').exists())
        self.assertEqual(len(list((self.f.root / 'her/episodes').rglob('*.md'))), 1)

    def test_clip_positive_and_negative_records_original(self):
        raw = self.f.proposal(delta=19)
        value = engine.guard(self.f.config, self.f.store, raw)
        self.assertEqual((value['delta'], value['original_delta']), (3, 19))
        raw['delta'] = -15
        value = engine.guard(self.f.config, self.f.store, raw)
        self.assertEqual((value['delta'], value['original_delta']), (-3, -15))

    def test_fewer_than_three_episodes_rejected(self):
        value = engine.guard(self.f.config, self.f.store, self.f.proposal(self.f.seed(2)))
        self.assertEqual(value['status'], 'rejected')
        self.assertIn('insufficient_episodes', value['codes'])

    def test_single_session_rejected(self):
        ids = []
        for i in range(3):
            value = self.f.candidate(i)
            value['source']['session'] = 'same-session'
            value['id'] = candidate_id(value)
            ids.append(self.f.emit(value))
        engine.consume(self.f.config, self.f.store)
        result = engine.guard(self.f.config, self.f.store, self.f.proposal(ids))
        self.assertIn('insufficient_sessions', result['codes'])

    def test_praise_only_rejected(self):
        ids = self.f.seed(praise_only=True)
        value = engine.guard(self.f.config, self.f.store, self.f.proposal(ids))
        self.assertEqual(value['status'], 'rejected')
        self.assertIn('praise_only', value['codes'])

    def test_private_and_unknown_evidence_rejected(self):
        ids = self.f.seed(sensitivity='private')
        value = engine.guard(self.f.config, self.f.store, self.f.proposal(ids))
        self.assertEqual(value['codes'], ['unknown_or_private_evidence'])

    def test_outside_range_pending(self):
        raw = self.f.proposal(delta=3)
        self.f.config.personality['traits']['curiosity']['value'] = 59
        value = engine.guard(self.f.config, self.f.store, raw)
        self.assertEqual(value['status'], 'pending')
        self.assertIn('outside_range', value['codes'])

    def test_monthly_gross_drift_pending_even_opposite_directions(self):
        raw = self.f.proposal(delta=-3)
        for index, delta in enumerate([3, -3, 3]):
            historical = {**raw, 'delta': delta}
            with self.f.store.db:
                self.f.store.db.execute('INSERT INTO proposals(id,document,status,applied_at) VALUES(?,?,?,?)',
                                       (str(index), canonical(historical), 'applied', now()))
        value = engine.guard(self.f.config, self.f.store, raw)
        self.assertEqual((value['drift_before'], value['status']), (9, 'pending'))

    def test_old_drift_excluded_and_threshold_from_lock(self):
        raw = self.f.proposal(delta=3)
        clock = datetime.now(timezone.utc)
        historical = {**raw, 'delta': 3}
        with self.f.store.db:
            self.f.store.db.execute('INSERT INTO proposals(id,document,status,applied_at) VALUES(?,?,?,?)',
                                   ('old', canonical(historical), 'applied', (clock - timedelta(days=31)).isoformat()))
        self.f.config.rules['monthly_drift_needs_approval'] = 2
        value = engine.guard(self.f.config, self.f.store, raw, clock)
        self.assertEqual(value['drift_before'], 0)
        self.assertEqual(value['status'], 'pending')

    def test_lock_missing_threshold_fails_closed(self):
        raw = self.f.proposal()
        del self.f.config.rules['min_evidence_episodes']
        with self.assertRaisesRegex(EngineError, 'lock_missing_or_invalid_min_evidence_episodes'):
            engine.guard(self.f.config, self.f.store, raw)

    def test_locked_write_and_path_traversal_denied(self):
        for name in ['persona.md', 'voice.md', 'identity-lock.yaml']:
            path = self.f.root / 'her' / name
            original = path.read_bytes()
            with self.assertRaisesRegex(EngineError, 'locked_file_write'):
                self.f.config.write(path, 'malicious')
            self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(EngineError):
            self.f.config.write(self.f.root / 'her/episodes/../../AGENTS.md', 'malicious')

    def test_locked_target_process_nonzero(self):
        path = str(self.f.cfg)
        code = "import sys; sys.path[:0]=" + repr([str(ROOT), str(ROOT.parent / 'conversation-processor')]) + "; from personality_engine.policy import Config; c=Config(" + repr(path) + "); c.write(c.root/'her/persona.md','forbidden')"
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', code], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'locked_file_write', result.stderr)

    def test_duplicate_evidence_cannot_satisfy_episode_minimum(self):
        ids = self.f.seed(2)
        value = engine.guard(self.f.config, self.f.store, self.f.proposal([ids[0], ids[1], ids[0]]))
        self.assertEqual(value['status'], 'rejected')

    def test_unsupported_trait_and_counter_evidence_rejected(self):
        raw = self.f.proposal(trait='unknown')
        self.assertEqual(engine.guard(self.f.config, self.f.store, raw)['codes'], ['unknown_trait'])
        raw['trait'] = 'curiosity'
        raw['counter_evidence'] = ['0' * 16]
        self.assertEqual(engine.guard(self.f.config, self.f.store, raw)['codes'], ['unknown_or_private_evidence'])

    def test_lock_changed_mid_run_stops_all_writes(self):
        path = self.f.root / 'her/identity-lock.yaml'
        path.write_text(path.read_text(encoding='utf-8') + '\nowner_revision: 2\n', encoding='utf-8')
        with self.assertRaisesRegex(EngineError, 'identity_lock_changed'):
            self.f.config.write(self.f.root / 'her/evolution/test.md', 'test')

    def test_concurrent_transaction_edit_not_overwritten(self):
        changes = {'her/evolution/test.md': 'engine content'}
        real = self.f.config.write

        def fail_before_write(*args):
            raise EngineError('synthetic_before_write')

        with patch.object(self.f.config, 'write', side_effect=fail_before_write):
            with self.assertRaises(EngineError):
                gitops.transaction(self.f.config, self.f.root, 'synthetic-write', changes, 'synthetic')
        target = self.f.root / 'her/evolution/test.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('concurrent owner content', encoding='utf-8')
        with self.assertRaisesRegex(EngineError, 'concurrent_file_edit'):
            gitops.transaction(self.f.config, self.f.root, 'synthetic-write', changes, 'synthetic')
        self.assertEqual(target.read_text(encoding='utf-8'), 'concurrent owner content')

    def test_rollback_recovery_after_revert_commit(self):
        value = self.f.ready(self.f.proposal())
        engine.apply(self.f.config, self.f.store, value['id'])
        row = self.f.store.db.execute('SELECT commit_sha FROM proposals WHERE id=?', (value['id'],)).fetchone()
        gitops.revert(self.f.config, value['id'], row['commit_sha'])
        sha = gitops.head(self.f.config, self.f.root)
        engine.rollback(self.f.config, self.f.store, value['id'])
        self.assertEqual(self.f.value(), 50)
        self.assertEqual(gitops.head(self.f.config, self.f.root), sha)

    def test_reflector_unavailable_preserves_watermark(self):
        self.f.seed()
        self.f.data['reflect_every'] = 3
        self.f.reload()
        with self.assertRaisesRegex(EngineError, 'local_reflector_unavailable'):
            engine.reflect(self.f.config, self.f.store)
        self.assertEqual(engine.status(self.f.config, self.f.store)['unreflected_normal'], 3)

    def test_sensitive_reflection_not_written_public(self):
        ids = self.f.seed()
        self.f.data['reflect_every'] = 3
        server = FakeHTTP(lambda body: approve_reviews(body, reason='secret-balance synthetic'))
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        with self.assertRaisesRegex(EngineError, 'sensitive_reflection_rejected'):
            engine.reflect(self.f.config, self.f.store)
        self.assertFalse((self.f.root / 'her/evolution/proposals').exists())
        self.assertFalse((self.f.config.cache / 'reflections').exists())

    def test_reflection_dry_run_with_full_batch_no_network_or_writes(self):
        self.f.seed()
        self.f.data['reflect_every'] = 3
        self.f.reload()
        before = {str(p): p.read_bytes() for p in self.f.folder.rglob('*') if p.is_file()}
        with patch.object(engine, 'local_reflection', side_effect=AssertionError('network')):
            self.assertTrue(engine.reflect(self.f.config, self.f.store, dry_run=True)['triggered'])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.f.folder.rglob('*') if p.is_file()})

    def test_reflection_evidence_outside_batch_rejected(self):
        ids = self.f.seed()
        self.f.data['reflect_every'] = 3
        raw = self.f.proposal(ids)
        raw['evidence'][0] = '0' * 16
        server = FakeHTTP({'proposals': [raw]})
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        with self.assertRaisesRegex(EngineError, 'invalid_reflection_response'):
            engine.reflect(self.f.config, self.f.store)
        self.assertEqual(engine.status(self.f.config, self.f.store)['unreflected_normal'], 3)
        self.assertEqual(self.f.value(), 50)

    def test_no_signal_for_trait_rejected(self):
        ids = self.f.seed(trait_signals=[])
        value = engine.guard(self.f.config, self.f.store, self.f.proposal(ids))
        self.assertEqual(value['status'], 'rejected')
        self.assertIn('unsupported_trait_evidence', value['codes'])

    def test_step_limit_is_read_from_lock(self):
        raw = self.f.proposal(delta=7)
        self.f.config.rules['max_step_per_trait'] = 1
        self.assertEqual(engine.guard(self.f.config, self.f.store, raw)['delta'], 1)

    def test_cli_dry_run_status_does_not_create_state(self):
        # An entirely separate synthetic cache path is unnecessary: the CLI
        # read-only path is exercised with a fresh metadata-free repository copy.
        folder = self.f.folder / 'readonly-instance'
        (folder / 'her').mkdir(parents=True)
        for name in ('identity-lock.yaml', 'personality.json'):
            (folder / 'her' / name).write_bytes((self.f.root / 'her' / name).read_bytes())
        data = {**self.f.data, 'repository': str(folder)}
        config = self.f.folder / 'readonly.yaml'
        config.write_text(yaml.safe_dump(data), encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'engine.py'), '--config', str(config), 'status', '--dry-run'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((folder / 'cache').exists())

    def test_reflection_batch_too_small_rejected(self):
        self.f.data['max_reflection_episodes'] = 19
        with self.assertRaisesRegex(EngineError, 'reflection_batch_smaller_than_trigger'):
            self.f.reload()

    def test_apply_one_commit_and_rollback_restores_without_deletion(self):
        value = self.f.ready(self.f.proposal(delta=3))
        result = engine.apply(self.f.config, self.f.store, value['id'])
        self.assertEqual(result['applied'], 1)
        self.assertEqual(self.f.value(), 53)
        row = self.f.store.db.execute('SELECT * FROM proposals WHERE id=?', (value['id'],)).fetchone()
        message = gitops.git(self.f.config, self.f.root, 'show', '-s', '--format=%s', row['commit_sha']).stdout.decode('utf-8').strip()
        self.assertEqual(message, 'xq-evolve: ' + value['id'] + ' curiosity +3')
        before = {p for p in (self.f.root / 'her').rglob('*') if p.is_file()}
        result = engine.rollback(self.f.config, self.f.store, value['id'])
        self.assertEqual(result['reverted'], 1)
        self.assertEqual(self.f.value(), 50)
        self.assertEqual(before, {p for p in (self.f.root / 'her').rglob('*') if p.is_file()})
        self.assertEqual(engine.rollback(self.f.config, self.f.store, value['id'])['unchanged'], 1)

    def test_pending_cannot_be_forced_by_apply(self):
        raw = self.f.proposal(delta=3)
        self.f.config.rules['monthly_drift_needs_approval'] = 2
        value = self.f.ready(raw)
        self.assertEqual(value['status'], 'pending')
        result = engine.apply(self.f.config, self.f.store, value['id'])
        self.assertEqual(result['applied'], 0)
        self.assertEqual(self.f.value(), 50)

    def test_dry_run_no_files_no_network_no_git(self):
        self.f.emit(self.f.candidate())
        before = {str(p): p.read_bytes() for p in self.f.folder.rglob('*') if p.is_file()}
        with patch.object(gitops, 'git', side_effect=AssertionError('git')), patch.object(engine, 'local_reflection', side_effect=AssertionError('network')):
            for command in ('collect', 'extract', 'reflect', 'status', 'apply'):
                engine.run(self.f.config, command, dry_run=True)
        after = {str(p): p.read_bytes() for p in self.f.folder.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_unrelated_staged_change_rejected(self):
        path = self.f.root / 'unrelated.md'
        path.write_text('owner work', encoding='utf-8')
        gitops.git(self.f.config, self.f.root, 'add', '--', 'unrelated.md')
        self.f.emit(self.f.candidate())
        with self.assertRaisesRegex(EngineError, 'unrelated_staged_changes'):
            engine.consume(self.f.config, self.f.store)
        self.assertFalse((self.f.root / 'her/episodes').exists())

    def test_reflection_trigger_local_http_and_auto_apply(self):
        ids = self.f.seed()
        self.f.data['reflect_every'] = 3
        server = FakeHTTP(approve_reviews)
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        result = engine.reflect(self.f.config, self.f.store)
        self.assertEqual(result['applied'], 1)
        self.assertEqual(self.f.value(), 51)
        self.assertEqual(len(server.requests), 1)
        self.assertNotIn('quotes', server.requests[0]['messages'][1]['content'])
        self.assertEqual(engine.reflect(self.f.config, self.f.store)['triggered'], False)

    def test_reflection_schema_invalid_no_watermark_advance(self):
        self.f.seed()
        self.f.data['reflect_every'] = 3
        server = FakeHTTP({'proposals': [{'trait': 'curiosity', 'delta': 'bad'}]})
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        with self.assertRaisesRegex(EngineError, 'invalid_reflection_response'):
            engine.reflect(self.f.config, self.f.store)
        self.assertEqual(engine.status(self.f.config, self.f.store)['unreflected_normal'], 3)

    def test_reflection_private_excluded_and_praise_rejected(self):
        ids = self.f.seed(praise_only=True)
        self.f.emit(self.f.candidate(9, sensitivity='private', summary='PRIVATE-NOT-FOR-REFLECTION'))
        engine.consume(self.f.config, self.f.store)
        self.f.data['reflect_every'] = 3
        server = FakeHTTP({'proposals': [self.f.proposal(ids)]})
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        result = engine.reflect(self.f.config, self.f.store)
        self.assertEqual((result['rejected'], result['applied']), (0, 0))
        self.assertEqual(server.requests, [])  # Pure praise yields no nomination or HTTP.
        document = self.f.store.db.execute('SELECT document FROM review_batches').fetchone()[0]
        self.assertNotIn('PRIVATE-NOT-FOR-REFLECTION', document)

    def test_reflector_external_endpoint_rejected(self):
        self.f.data['reflector']['base_url'] = 'http://198.51.100.1/v1'
        with self.assertRaises(ValueError):
            self.f.reload()

    def test_consume_crash_after_git_commit_is_idempotent(self):
        value = self.f.candidate()
        self.f.emit(value)
        real = gitops.transaction

        def fail_after(*args):
            real(*args)
            raise EngineError('synthetic_after_commit')

        with patch.object(gitops, 'transaction', side_effect=fail_after):
            with self.assertRaisesRegex(EngineError, 'synthetic_after_commit'):
                engine.consume(self.f.config, self.f.store)
        sha = gitops.head(self.f.config, self.f.root)
        self.assertEqual(engine.consume(self.f.config, self.f.store)['consumed'], 1)
        self.assertEqual(sha, gitops.head(self.f.config, self.f.root))

    def test_apply_crash_after_commit_recovers_once(self):
        value = self.f.ready(self.f.proposal(delta=2))
        # Bootstrap log first so the simulated crash targets proposal commit.
        gitops.transaction(self.f.config, self.f.root, 'initialize:evolution-log',
                           {'her/evolution/log.md': '# 人格演化记录\n'}, 'xq-memory: initialize evolution log')
        real = gitops.transaction

        def fail_after(*args):
            real(*args)
            raise EngineError('synthetic_after_commit')

        with patch.object(gitops, 'transaction', side_effect=fail_after):
            with self.assertRaises(EngineError):
                engine.apply(self.f.config, self.f.store, value['id'])
        self.assertEqual(self.f.value(), 52)
        sha = gitops.head(self.f.config, self.f.root)
        engine.apply(self.f.config, self.f.store, value['id'])
        self.assertEqual(self.f.value(), 52)
        self.assertEqual(sha, gitops.head(self.f.config, self.f.root))

    def test_processor_cli_api_sim_end_to_end(self):
        sim = self.f.folder / 'sim'
        sim.mkdir()
        file = sim / 'synthetic.jsonl'
        file.write_text('', encoding='utf-8')
        self.f.proc['sources'] = [{'id': 'test', 'kind': 'sim', 'path': str(sim), 'pattern': '*.jsonl', 'enabled': True}]
        payload = {key: value for key, value in self.f.candidate().items() if key not in ('schema', 'id', 'source', 'persona_hash')}
        server = FakeHTTP(payload)
        self.addCleanup(server.close)
        self.f.proc['extractor']['base_url'] = server.url
        self.f.reload()
        pipeline.baseline(processor_load(self.f.proc_cfg))  # synthetic only
        unit = {'source': {'kind': 'sim', 'session': 'integration', 'refs': ['turn:1'],
                           'source_time': now(), 'observed_at': now()}, 'persona_hash': '12345678',
                'user': 'Synthetic question.', 'assistant': 'Synthetic answer.'}
        file.write_text(canonical(unit) + '\n', encoding='utf-8')
        engine.run(self.f.config, 'collect')
        result = engine.run(self.f.config, 'extract')
        self.assertEqual(result['candidates']['normal'], 1)
        self.assertEqual(engine.run(self.f.config, 'extract')['candidates']['duplicate'], 1)


if __name__ == '__main__':
    unittest.main()
