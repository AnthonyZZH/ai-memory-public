"""Directional nomination and owner-only expression regressions; synthetic only."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
import yaml
from test_engine import Fixture, FakeHTTP, approve_reviews
from personality_engine import engine, reflection, gitops
from personality_engine.policy import EngineError, canonical


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(personality={'traits': {'curiosity': {}}},
            threshold=lambda key: {'min_evidence_episodes': 3, 'min_evidence_sessions': 2}[key])

    def episodes(self, positive=3, negative=0, sessions=2, praise=0):
        return [{'id': format(i, '016x'), 'source': {'kind': 'sim', 'session': str(i % sessions)},
                 'praise_only': i < praise,
                 'trait_signals': [{'trait': 'curiosity', 'direction': 1 if i < positive else -1}]}
                for i in range(positive + negative)]

    def nominate(self, **kwargs):
        return reflection.nominate(self.config, self.episodes(**kwargs), 'synthetic')[0]

    def test_exact_episode_and_session_thresholds(self):
        self.assertEqual(len(self.nominate()), 1)
        self.assertEqual(self.nominate(positive=2), [])
        self.assertEqual(self.nominate(sessions=1), [])

    def test_opposition_one_third_boundary_without_float_rounding(self):
        self.assertEqual(len(self.nominate(positive=3, negative=1)), 1)
        self.assertEqual(self.nominate(positive=3, negative=2), [])
        self.assertEqual(len(self.nominate(positive=4, negative=1)), 1)
        self.assertEqual(self.nominate(positive=5, negative=2), [])

    def test_negative_direction_and_one_candidate_per_trait(self):
        nominated = self.nominate(positive=1, negative=3)
        self.assertEqual([p['delta'] for p in nominated], [-1])
        self.assertEqual(self.nominate(positive=3, negative=3), [])

    def test_praise_removed_before_all_counts(self):
        self.assertEqual(self.nominate(praise=1), [])
        self.assertEqual(len(self.nominate(positive=4, praise=1)), 1)

    def test_duplicate_episode_ids_cannot_pad_counts(self):
        rows = self.episodes(positive=2)
        self.assertEqual(reflection.nominate(self.config, rows + rows, 'synthetic')[0], [])

    def test_review_cannot_add_change_or_omit_candidates(self):
        candidates = self.nominate()
        valid = {'reviews': [{'id': candidates[0]['id'], 'decision': 'approve', 'reason': 'Grounded.'}]}
        self.assertIsNone(reflection.validate(valid, candidates))
        for field, value in [('delta', 3), ('trait', 'invented'), ('evidence', []), ('proposals', [])]:
            bad = deepcopy(valid)
            bad['reviews'][0][field] = value
            self.assertIsNotNone(reflection.validate(bad, candidates))
        for bad in ({'reviews': []}, {'reviews': valid['reviews'] * 2},
                    {'reviews': [{**valid['reviews'][0], 'id': 'f' * 16}]},
                    {'reviews': [{**valid['reviews'][0], 'decision': 'modify'}]}):
            self.assertIsNotNone(reflection.validate(bad, candidates))

    def test_duplicate_review_ids_rejected_by_code_even_with_valid_schema(self):
        candidates = self.nominate()
        candidates.append({**candidates[0], 'id': 'f' * 16})
        value = {'reviews': [{'id': candidates[0]['id'], 'decision': 'approve', 'reason': 'ok'}] * 2}
        self.assertTrue(reflection.validator(candidates).is_valid(value))
        self.assertIsNotNone(reflection.validate(value, candidates))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)
        self.f.data['reflect_every'] = 3
        self.f.proc['expressions'] = {'non_owner_markers': ['group chat', 'third-party'],
                                     'aggressive_keywords': ['idiot', 'moron']}
        self.f.reload()

    def server(self, value):
        server = FakeHTTP(value)
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        return server

    def test_failure_retains_frozen_batch_then_approves_without_reusing_new_turn(self):
        self.f.seed()
        with self.assertRaisesRegex(EngineError, 'local_reflector_unavailable'):
            engine.reflect(self.f.config, self.f.store)
        frozen = self.f.store.db.execute('SELECT id,document,status FROM review_batches').fetchone()
        self.assertEqual(frozen['status'], 'pending')
        self.assertEqual(self.f.value(), 50)
        self.f.emit(self.f.candidate(10))
        engine.consume(self.f.config, self.f.store)
        server = self.server(approve_reviews)
        self.assertEqual(engine.reflect(self.f.config, self.f.store)['applied'], 1)
        sent = json.loads(server.requests[0]['messages'][1]['content'])
        self.assertEqual(sent['candidates'], json.loads(frozen['document'])['candidates'])
        self.assertEqual(len(sent['episodes']), 3)
        self.assertEqual(engine.status(self.f.config, self.f.store)['unreflected_normal'], 1)
        self.assertEqual(self.f.value(), 51)
        self.assertFalse(engine.reflect(self.f.config, self.f.store)['triggered'])

    def test_veto_never_applies_and_cannot_be_bypassed_by_apply(self):
        self.f.seed()
        self.server(lambda body: approve_reviews(body, decision='veto', reason='Identity rule compliance.'))
        result = engine.reflect(self.f.config, self.f.store)
        self.assertEqual((result['rejected'], result['applied']), (1, 0))
        self.assertEqual(engine.apply(self.f.config, self.f.store)['applied'], 0)
        self.assertEqual(self.f.value(), 50)

    def test_invalid_review_retained_and_no_watermark_advance(self):
        self.f.seed()
        self.server(lambda body: {'reviews': [{**approve_reviews(body)['reviews'][0], 'delta': 3}]})
        with self.assertRaisesRegex(EngineError, 'invalid_reflection_response'):
            engine.reflect(self.f.config, self.f.store)
        self.assertEqual(engine.status(self.f.config, self.f.store)['unreflected_normal'], 3)
        self.assertEqual(self.f.store.db.execute("SELECT count(*) FROM review_batches WHERE status='pending'").fetchone()[0], 1)
        self.assertEqual(self.f.store.db.execute('SELECT count(*) FROM proposals').fetchone()[0], 0)

    def test_apply_rechecks_review_approval(self):
        raw = self.f.proposal()
        raw.update(origin='deterministic/v1', id='a' * 16,
                   review={'id': 'a' * 16, 'decision': 'veto', 'reason': 'Not growth.'})
        self.assertEqual(engine.guard(self.f.config, self.f.store, raw)['codes'], ['review_not_approved'])

    def test_engine_rechecks_group_and_aggression_at_consumption(self):
        for i, text in enumerate(('idiot', 'Friendly group phrase')):
            value = self.f.candidate(i, category='expression', expression=text)
            if i:
                value['source']['audience'] = 'group'
            self.f.emit(value)
        counts = engine.consume(self.f.config, self.f.store)
        self.assertEqual((counts['invalid'], counts['consumed']), (2, 0))
        self.assertFalse((self.f.root / 'her/evolution/expressions.md').exists())

    def test_next_normal_write_cleans_legacy_and_blocked_entries_without_deleting_file(self):
        entries = [{'key': str(i), 'text': text, 'last_seen': '2026-10-28T00:00:00+00:00', **meta}
                   for i,(text,meta) in enumerate((('Unknown legacy', {}), ('An idiot', {'audience':'owner'}),
                       ('Group saying', {'audience':'group'}), ('Friendly owner saying', {'audience':'owner'})))]
        text = '---\n' + yaml.safe_dump({'entries':entries}) + '---\n'
        gitops.transaction(self.f.config, self.f.root, 'fixture:expressions',
                           {'her/evolution/expressions.md':text}, 'synthetic expressions')
        self.f.seed()
        path = self.f.root / 'her/evolution/expressions.md'
        self.assertTrue(path.exists())
        saved = yaml.safe_load(path.read_text(encoding='utf-8').split('---',2)[1])['entries']
        self.assertEqual([e['text'] for e in saved], ['Friendly owner saying'])
