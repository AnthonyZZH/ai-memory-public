"""Strictness regressions; all candidates and repositories are synthetic."""
import unittest
from test_engine import Fixture, FakeHTTP
from personality_engine import engine
from personality_engine.policy import EngineError


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def seed_mixed(self, count, sessions):
        ids = []
        for i, (praise, session) in enumerate(zip(count, sessions)):
            value = self.f.candidate(i, praise_only=praise)
            value['source']['session'] = session
            from conversation_processor.common import candidate_id
            value['id'] = candidate_id(value)
            ids.append(self.f.emit(value))
        engine.consume(self.f.config, self.f.store)
        return ids

    def test_praise_cannot_pad_episode_count_even_when_owner_approved(self):
        ids = self.seed_mixed([False, False, True, True], ['a', 'b', 'c', 'd'])
        for approved in (False, True):
            value = engine.guard(self.f.config, self.f.store, self.f.proposal(ids), owner_approved=approved)
            self.assertEqual(value['status'], 'rejected')
            self.assertIn('insufficient_nonpraise_episodes', value['codes'])

    def test_praise_cannot_pad_session_count(self):
        ids = self.seed_mixed([False, False, False, True], ['a', 'a', 'a', 'b'])
        value = self.f.ready(self.f.proposal(ids))
        self.assertEqual(value['status'], 'rejected')
        self.assertIn('insufficient_nonpraise_sessions', value['codes'])
        self.assertNotIn('insufficient_nonpraise_episodes', value['codes'])

    def test_genuine_evidence_survives_mixed_praise(self):
        ids = self.seed_mixed([False, False, False, True], ['a', 'a', 'b', 'c'])
        value = self.f.ready(self.f.proposal(ids))
        self.assertEqual(value['status'], 'ready')

    def test_reflection_schema_repaired_once(self):
        server = FakeHTTP(lambda body: {'reviews': 'wrong'} if len(body['messages']) == 2 else {'reviews': []})
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        self.assertEqual(engine.local_reflection(self.f.config, [], []), {'reviews': []})
        self.assertEqual(len(server.requests), 2)
        self.assertIn('validator=type', server.requests[1]['messages'][-1]['content'])

    def test_reflection_schema_second_failure_is_rejected(self):
        server = FakeHTTP({'proposals': 'wrong'})
        self.addCleanup(server.close)
        self.f.data['reflector']['base_url'] = server.url
        self.f.reload()
        with self.assertRaisesRegex(EngineError, 'invalid_reflection_response'):
            engine.local_reflection(self.f.config, [], [])
        self.assertEqual(len(server.requests), 2)
