"""Synthetic V2.2c fixtures only: no live snapshots, toasts or model controls."""
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

import yaml

from test_engine import Fixture, ROOT
sys.path.insert(0, str(ROOT.parent))
import persona_loader as loader
from personality_engine import daily, engine, gitops, notify, snapshots
from personality_engine.policy import Config, EngineError, canonical, digest


def retained(prefix):
    base = Path('E:/Codex Development/tmp/v2.2c')
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=base))


def files(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = retained('loader-')
        (self.folder / 'persona.md').write_text('---\nstatus: finalized\n---\n## Core\n- Ask before guessing.「source」\n> finalized owner note\n## Empty\n-\n', encoding='utf-8')
        (self.folder / 'voice.md').write_text('## Voice\n- Short.\n', encoding='utf-8')

    def add(self, name, value):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')

    def test_legacy_cleaning_empty_sections_source_and_three_targets(self):
        content = loader.load_persona(self.folder)
        self.assertNotIn('status:', content)
        self.assertNotIn('finalized owner', content)
        self.assertNotIn('Empty', content)
        self.assertNotIn('source', content)
        self.assertIn('「source」', loader.load_persona(self.folder, True))
        tails = [loader.render_persona(content, target, self.folder).splitlines()[-1] for target in ('local', 'dsh', 'steward')]
        self.assertEqual(len(set(tails)), 1)

    def test_all_32_optional_section_combinations(self):
        for mask in range(32):
            path = self.folder / str(mask)
            path.mkdir()
            for name in ('persona.md', 'voice.md'):
                (path / name).write_bytes((self.folder / name).read_bytes())
            if mask & 1:
                (path / 'identity-lock.yaml').write_text('identity: [Synthetic identity]\nprinciples: [Keep boundaries]\n', encoding='utf-8')
            if mask & 2 or mask & 16:
                (path / 'personality.json').write_text(json.dumps({'traits': {'curiosity': {'value': 50}}}), encoding='utf-8')
            if mask & 4:
                (path / 'evolution').mkdir(exist_ok=True)
                (path / 'evolution/expressions.md').write_text('---\nentries:\n- text: Synthetic saying\n---\n', encoding='utf-8')
            if mask & 8:
                (path / 'relationship.md').write_text('## Observations\n- A recent summary.\n## Relations\n', encoding='utf-8')
            if mask & 16:
                pending = path / 'evolution/proposals/pending'
                pending.mkdir(parents=True)
                (pending / 'synthetic.json').write_text(json.dumps({'trait': 'curiosity', 'delta': 2, 'status': 'pending'}), encoding='utf-8')
            content = loader.load_persona(path)
            self.assertEqual('Synthetic identity' in content, bool(mask & 1))
            self.assertEqual('curiosity50' in content, bool(mask & 2 or mask & 16))
            self.assertEqual('Synthetic saying' in content, bool(mask & 4))
            self.assertEqual('A recent summary.' in content, bool(mask & 8))
            self.assertEqual('等主人批准' in content, bool(mask & 16))
            for target in ('local', 'dsh', 'steward'):
                rendered = loader.render_persona(content, target, path)
                self.assertEqual('Synthetic identity' in rendered, bool(mask & 1))

    def test_empty_core_still_errors_even_with_identity(self):
        self.add('persona.md', '# Empty\n-\n')
        self.add('voice.md', '> note\n## Empty\n-\n')
        self.add('identity-lock.yaml', 'identity: [Synthetic]\n')
        with self.assertRaisesRegex(ValueError, '人格内容为空'):
            loader.load_persona(self.folder)

    def test_relationship_recent_600_and_trimmed_before_expression(self):
        self.add('relationship.md', '## Observations\n- oldest ' + 'a' * 700 + '\n- newest-summary\n## Relations\n')
        self.add('evolution/expressions.md', '- keep-expression\n')
        full = loader.load_persona(self.folder)
        body = full.split('## 最近相处摘要\n\n')[1]
        self.assertLessEqual(len(body), 600)
        self.assertIn('newest-summary', body)
        self.assertNotIn('oldest', body)
        limited = loader.load_persona(self.folder, max_chars=len(full) - 300)
        self.assertLessEqual(len(limited), len(full) - 300)
        self.assertIn('keep-expression', limited)
        self.assertIn('newest-summary', limited)
        for target in ('local', 'dsh', 'steward'):
            self.assertLessEqual(len(loader.render_persona(limited, target, self.folder)), len(full) - 300)

    def test_core_never_silently_truncated(self):
        self.add('identity-lock.yaml', 'principles: [' + 'x' * 500 + ']\n')
        with self.assertRaisesRegex(ValueError, '人格核心超过'):
            loader.load_persona(self.folder, max_chars=100)

    def test_every_extension_changes_shared_hash_and_pending_is_sanitized(self):
        previous = hashlib.sha256(loader.load_persona(self.folder).encode()).hexdigest()
        additions = [('identity-lock.yaml', 'identity: [Synthetic]\nprinciples: [Independent]\n'),
                     ('personality.json', json.dumps({'traits': {'curiosity': {'value': 50}}})),
                     ('evolution/expressions.md', '- A new saying\n'),
                     ('relationship.md', '- A new summary\n'),
                     ('evolution/proposals/pending/p.json', json.dumps({'trait': 'curiosity', 'delta': -2, 'reason': 'SECRET-REASON', 'evidence': ['SECRET-ID']}))]
        for name, value in additions:
            self.add(name, value)
            content = loader.load_persona(self.folder)
            current = hashlib.sha256(content.encode()).hexdigest()
            self.assertNotEqual(previous, current)
            self.assertNotIn('SECRET', content)
            previous = current
        self.assertIn('curiosity -2', content)
        self.add('evolution/proposals/pending/p.json', json.dumps({'trait': 'curiosity', 'delta': -2, 'status': 'rejected'}))
        self.assertNotIn('等主人批准', loader.load_persona(self.folder))

    def test_empty_optional_files_and_invalid_extension(self):
        self.add('identity-lock.yaml', '')
        self.add('evolution/expressions.md', '')
        self.add('relationship.md', '')
        self.assertNotIn('## 底线', loader.load_persona(self.folder))
        self.add('identity-lock.yaml', 'identity: [broken')
        with self.assertRaises(ValueError):
            loader.load_persona(self.folder)


class DailyHTTPTests(unittest.TestCase):
    def server(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                calls.append(self.path)
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/must-not-follow')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, body))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"state":"starting","job_profile":"fixture"}')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:' + str(server.server_port), calls

    def test_actual_local_http_health_and_start_payload(self):
        base, calls = self.server()
        self.assertTrue(daily.healthy({'model_url': base}))
        self.assertEqual(daily.request(base, '/model/start', {'profile': 'fixture'})['job_profile'], 'fixture')
        self.assertEqual(calls, ['/health', ('/model/start', {'profile': 'fixture'})])

    def test_daily_http_redirect_and_nonloopback_rejected(self):
        base, calls = self.server()
        with self.assertRaises(EngineError):
            daily.request(base, '/redirect')
        self.assertEqual(calls, ['/redirect'])
        with self.assertRaises(ValueError):
            daily.request('http://198.51.100.1', '/health')


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def snapshots(self, block=False):
        directory = self.f.folder / 'snapshots'
        directory.mkdir()
        old_local = '以下为人格与说话方式设定：\n\nOld 😺 persona\n\n[persona sha256=12345678 字数=12]'
        old_dsh = '<persona>\nOld persona\n</persona>\n\n[persona sha256=12345678 字数=12]'
        targets = []
        for i, suffix in enumerate(['', '\n\nLIBRARY-RULES: keep every byte.\r\nSpacing  untouched.']):
            path = directory / ('lm-' + str(i) + '.json')
            doc = {'operation': {'fields': [{'key': 'temperature', 'value': 0.8}, {'key': 'llm.prediction.systemPrompt', 'value': old_local + suffix}]}, 'token': 'FAKE-CREDENTIAL'}
            raw = json.dumps(doc, ensure_ascii=i == 1, indent=2).replace('\n', '\r\n').encode('utf-8')
            path.write_bytes(raw)
            targets.append({'id': 'lm-' + str(i), 'kind': 'lmstudio', 'path': str(path)})
        path = directory / 'dsh.yml'
        doc = [{'config': {'model': 'unchanged', 'apiKey': 'FAKE-CREDENTIAL'}},
               {'insert': [{'id': 'preset-fixture', 'config': {'id': 'fixture', 'plugins': [{'id': 'persona', 'config': {'prefix': old_dsh}}, {'id': 'tools', 'config': {'enabled': True}}]}}]}]
        text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        if block:
            node = snapshots.yaml_node(yaml.compose(text), (1, 'insert', 0, 'config', 'plugins', 0, 'config', 'prefix'))
            column = node.start_mark.column
            # Same-line scalar position is after prefix:, body is indented two
            # spaces beyond the key column, not beyond the value column.
            indentation = text[text.rfind('\n', 0, node.start_mark.index) + 1:node.start_mark.index]
            spaces = len(indentation) - len(indentation.lstrip()) + 2
            text = text[:node.start_mark.index] + '|-\n' + '\n'.join(' ' * spaces + line for line in old_dsh.splitlines()) + text[node.end_mark.index:]
        path.write_text(text, encoding='utf-8', newline='')
        targets.append({'id': 'dsh-fixture', 'kind': 'dsh', 'path': str(path), 'preset': 'fixture'})
        self.f.data['sync'] = {'targets': targets}
        self.f.reload()
        return targets

    def test_sync_preserves_rules_credentials_other_bytes_and_noop_zero_writes(self):
        targets = self.snapshots()
        before = [Path(t['path']).read_bytes() for t in targets]
        result = snapshots.sync(self.f.config)
        self.assertEqual(result['written'], 3)
        backup = Path(result['backup'])
        self.assertEqual(len(list(backup.iterdir())), 3)
        for t, raw in zip(targets, before):
            self.assertEqual((backup / (t['id'] + '-' + Path(t['path']).name)).read_bytes(), raw)
            new = Path(t['path']).read_bytes()
            self.assertIn(b'FAKE-CREDENTIAL', new)
            self.assertTrue(snapshots.replace(new, t, loader.render_persona(loader.load_persona(self.f.root / 'her'), 'local' if t['kind'] == 'lmstudio' else 'dsh', self.f.root / 'her'))[0] == new)
        library = Path(targets[1]['path']).read_bytes()
        self.assertEqual(before[1].split(b'LIBRARY-RULES:')[1], library.split(b'LIBRARY-RULES:')[1])
        state = files(self.f.folder)
        second = snapshots.sync(self.f.config)
        self.assertEqual((second['changed'], second['written']), (0, 0))
        self.assertEqual(state, files(self.f.folder))

    def test_sync_yaml_block_scalar(self):
        self.snapshots(block=True)
        self.assertEqual(snapshots.sync(self.f.config)['written'], 3)

    def test_sync_dry_run_writes_nothing(self):
        self.snapshots()
        before = files(self.f.folder)
        self.assertEqual(snapshots.sync(self.f.config, True)['changed'], 3)
        self.assertEqual(before, files(self.f.folder))

    def test_sync_external_mtime_change_aborts_before_any_write(self):
        targets = self.snapshots()
        first = Path(targets[0]['path'])
        originals = [Path(t['path']).read_bytes() for t in targets]
        original = snapshots.fingerprint
        count = 0

        def mutate(path):
            nonlocal count
            count += 1
            if count == 4:
                stat = first.stat()
                os.utime(first, ns=(stat.st_atime_ns, stat.st_mtime_ns + 100000000))
            return original(path)

        with patch.object(snapshots, 'fingerprint', side_effect=mutate):
            with self.assertRaisesRegex(EngineError, 'sync_concurrent_edit'):
                snapshots.sync(self.f.config)
        self.assertEqual(originals, [Path(t['path']).read_bytes() for t in targets])
        self.assertFalse((self.f.root / 'backups').exists())

    def test_sync_hash_change_with_preserved_mtime_aborts(self):
        targets = self.snapshots()
        first = Path(targets[0]['path'])
        original = snapshots.fingerprint
        count = 0

        def mutate(path):
            nonlocal count
            count += 1
            if count == 4:
                stat = first.stat()
                first.write_bytes(first.read_bytes().replace(b'FAKE-CREDENTIAL', b'OTHER-CREDENTIAL'))
                os.utime(first, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            return original(path)

        with patch.object(snapshots, 'fingerprint', side_effect=mutate):
            with self.assertRaisesRegex(EngineError, 'sync_concurrent_edit'):
                snapshots.sync(self.f.config)
        self.assertFalse((self.f.root / 'backups').exists())

    def test_sync_rejects_locked_target(self):
        self.snapshots()
        self.f.config.data['sync']['targets'][0]['path'] = str(self.f.root / 'her/persona.md')
        with self.assertRaisesRegex(EngineError, 'sync_target_not_allowed'):
            snapshots.sync(self.f.config)

    def test_approve_requires_flag_and_keeps_all_strong_guards(self):
        ids = self.f.seed(praise_only=True)
        raw = self.f.proposal(ids)
        value = {**raw, 'id': digest(raw)[:16], 'status': 'pending'}
        engine.store_proposal(self.f.config, self.f.store, value)
        with self.assertRaisesRegex(EngineError, 'owner_approval_flag_required'):
            engine.review(self.f.config, self.f.store, value['id'], True)
        result = engine.review(self.f.config, self.f.store, value['id'], True, owner_approved=True)
        self.assertEqual((result['applied'], result['rejected']), (0, 1))
        self.assertEqual(self.f.value(), 50)
        self.assertEqual(loader.pending_changes(self.f.root / 'her'), [])

    def test_approve_skips_only_drift_clips_delta_and_clears_reminder(self):
        self.f.config.rules['monthly_drift_needs_approval'] = 2
        value = self.f.ready(self.f.proposal(delta=19))
        self.assertEqual(value['status'], 'pending')
        self.assertEqual(len(loader.pending_changes(self.f.root / 'her')), 1)
        result = engine.review(self.f.config, self.f.store, value['id'], True, owner_approved=True)
        self.assertEqual(result['applied'], 1)
        self.assertEqual(self.f.value(), 53)
        document = json.loads(self.f.store.db.execute('SELECT document FROM proposals WHERE id=?', (value['id'],)).fetchone()[0])
        self.assertEqual(document['original_delta'], 19)
        self.assertIn('monthly_drift', document['owner_overrides'])
        self.assertEqual(loader.pending_changes(self.f.root / 'her'), [])
        self.assertEqual(engine.review(self.f.config, self.f.store, value['id'], True, True)['unchanged'], 1)

    def test_owner_approved_outside_trait_range_remains_loadable_and_rollback(self):
        personality = deepcopy(self.f.personality)
        personality['traits']['curiosity']['value'] = 59
        gitops.transaction(self.f.config, self.f.root, 'synthetic-range-start', {'her/personality.json': json.dumps(personality) + '\n'}, 'synthetic state')
        self.f.reload()
        value = self.f.ready(self.f.proposal(delta=3))
        self.assertEqual(value['status'], 'pending')
        engine.review(self.f.config, self.f.store, value['id'], True, True)
        self.assertEqual(self.f.value(), 62)
        self.assertEqual(Config(self.f.cfg).personality['traits']['curiosity']['value'], 62)
        engine.rollback(self.f.config, self.f.store, value['id'])
        self.assertEqual(self.f.value(), 59)

    def test_reject_requires_flag_and_retains_audit_file(self):
        self.f.config.rules['monthly_drift_needs_approval'] = 2
        value = self.f.ready(self.f.proposal(delta=3))
        with self.assertRaises(EngineError):
            engine.review(self.f.config, self.f.store, value['id'], False)
        engine.review(self.f.config, self.f.store, value['id'], False, True)
        path = self.f.root / 'her/evolution/proposals/pending' / (value['id'] + '.json')
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['status'], 'rejected')
        self.assertEqual(loader.pending_changes(self.f.root / 'her'), [])
        self.assertEqual(self.f.value(), 50)

    def test_notifications_fail_without_blocking_pending(self):
        self.f.config.rules['monthly_drift_needs_approval'] = 2
        with patch.object(notify, 'pending', side_effect=OSError('synthetic notification error')):
            value = self.f.ready(self.f.proposal(delta=3))
        self.assertEqual(self.f.store.db.execute('SELECT status FROM proposals WHERE id=?', (value['id'],)).fetchone()[0], 'pending')

    def test_toast_payload_has_only_dimensions_deltas_and_failure_is_false(self):
        self.f.config.data['notifications'] = {'enabled': True}
        with patch.object(notify.subprocess, 'run', side_effect=OSError('unavailable')) as call:
            self.assertFalse(notify.pending(self.f.config, [{'trait': 'curiosity', 'delta': 2, 'reason': 'SECRET', 'evidence': ['SECRET']}]))
        if os.name == 'nt':
            import base64
            script = base64.b64decode(call.call_args[0][0][-1]).decode('utf-16le')
            self.assertNotIn('SECRET', script)
            self.assertIn('Windows.UI.Notifications', script)

    def daily_settings(self):
        runtime = self.f.folder / 'runtime'
        runtime.mkdir()
        self.f.config.data['daily'] = {'model_url': 'http://127.0.0.1:1', 'control_url': 'http://127.0.0.1:2',
                                      'runtime_directory': str(runtime), 'start_timeout_seconds': 2,
                                      'stop_timeout_seconds': 2, 'poll_seconds': 0}
        return runtime

    def test_daily_dry_run_zero_files_http_processes(self):
        self.daily_settings()
        before = files(self.f.folder)
        with patch.object(daily, 'request', side_effect=AssertionError('HTTP')), patch.object(daily, 'engine_run', side_effect=AssertionError('engine')):
            self.assertEqual(daily.run(self.f.config, True)['code'], 'preview')
        self.assertEqual(before, files(self.f.folder))

    def test_daily_existing_model_never_stops_and_logs_no_body(self):
        self.daily_settings()
        with (patch.object(daily, 'healthy', return_value=True),
              patch.object(daily, 'request', side_effect=AssertionError('control')),
              patch.object(daily, 'engine_run', return_value={'consumed': 1, 'reason': 'SECRET-BODY'})):
            result = daily.run(self.f.config)
        self.assertEqual((result['code'], result['started'], result['stopped']), ('ok', 0, 0))
        log = (self.f.root / 'cache/xq-daily.log').read_text(encoding='utf-8')
        self.assertNotIn('SECRET', log)

    def test_daily_owned_model_stops_even_on_pipeline_failure(self):
        runtime = self.daily_settings()
        state = {'up': False, 'stop': 0}

        def request(base, path, body=None):
            if path == '/model/start':
                state['up'] = True
                (runtime / 'fixture-profile.json').write_text('{"token":"FAKE"}', encoding='utf-8')
                return {'state': 'starting', 'job_profile': 'fixture-profile'}
            if path == '/model/stop':
                state['stop'] += 1
                state['up'] = False
                return {'state': 'stopping'}
            return {'state': 'ready' if state['up'] else 'stopped', 'selected': 'fixture-profile', 'running': 'fixture-profile' if state['up'] else None}

        def phase(config, command):
            if command == 'sync':
                return {'changed': 0}
            raise EngineError('synthetic_phase_failed')

        with patch.object(daily, 'request', side_effect=request), patch.object(daily, 'healthy', side_effect=lambda settings: state['up']), patch.object(daily, 'engine_run', side_effect=phase):
            result = daily.run(self.f.config)
        self.assertEqual((result['started'], result['stopped'], state['stop']), (1, 1, 1))
        self.assertEqual(result['code'], 'synthetic_phase_failed')

    def test_daily_external_restart_prevents_stop(self):
        runtime = self.daily_settings()
        state = {'up': False, 'stop': 0}

        def request(base, path, body=None):
            if path == '/model/start':
                state['up'] = True
                (runtime / 'fixture-profile.json').write_text('{"token":"FAKE-INITIAL"}', encoding='utf-8')
                return {'state': 'starting', 'job_profile': 'fixture-profile'}
            if path == '/model/stop':
                state['stop'] += 1
            return {'state': 'ready' if state['up'] else 'stopped', 'selected': 'fixture-profile', 'running': 'fixture-profile' if state['up'] else None}

        def phase(config, command):
            if command == 'apply':
                (runtime / 'fixture-profile.json').write_text('{"token":"FAKE-RESTART"}', encoding='utf-8')
            return {'changed': 0}

        with patch.object(daily, 'request', side_effect=request), patch.object(daily, 'healthy', side_effect=lambda settings: state['up']), patch.object(daily, 'engine_run', side_effect=phase):
            result = daily.run(self.f.config)
        self.assertEqual((state['stop'], result['code']), (0, 'daily_restore_failed'))

    def test_new_pending_and_owner_decision_auto_sync_snapshots(self):
        self.snapshots()
        self.f.config.data['sync']['automatic'] = True
        self.f.config.rules['monthly_drift_needs_approval'] = 2
        ids = self.f.seed()
        # A ready proposal can become pending when rechecked against new drift.
        raw = self.f.proposal(ids, delta=3)
        value = {**raw, 'id': digest(raw)[:16], 'status': 'ready'}
        engine.store_proposal(self.f.config, self.f.store, value)
        with patch.object(engine, 'guard', wraps=engine.guard):
            result = engine.run(self.f.config, 'apply', value['id'])
        self.assertEqual(result['sync']['written'], 3)
        prompt = json.loads(Path(self.f.config.data['sync']['targets'][0]['path']).read_bytes())['operation']['fields'][1]['value']
        self.assertIn('等主人批准', prompt)
        result = engine.run(self.f.config, 'reject', value['id'], owner_approved=True)
        self.assertEqual(result['sync']['written'], 3)
        prompt = json.loads(Path(self.f.config.data['sync']['targets'][0]['path']).read_bytes())['operation']['fields'][1]['value']
        self.assertNotIn('等主人批准', prompt)

    def test_auto_sync_failure_reports_without_undoing_committed_change(self):
        self.snapshots()
        self.f.config.data['sync']['automatic'] = True
        value = self.f.ready(self.f.proposal())
        with patch.object(snapshots, 'sync', side_effect=EngineError('sync_concurrent_edit')):
            with self.assertRaisesRegex(EngineError, 'automatic_sync_failed'):
                engine.run(self.f.config, 'apply', value['id'])
        self.assertEqual(self.f.value(), 51)
        self.assertEqual(snapshots.sync(self.f.config)['written'], 3)


if __name__ == '__main__':
    unittest.main()
