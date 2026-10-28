"""Deterministic directional statistics followed by a bounded model veto gate."""
from copy import deepcopy
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from conversation_processor.config import local_endpoint
from .policy import EngineError, canonical, digest

ROOT = Path(__file__).resolve().parent
REVIEW_SCHEMA = json.loads((ROOT / 'review.schema.json').read_text(encoding='utf-8'))


def nominate(config, episodes, batch):
    episodes = list({r['id']: r for r in episodes if not r['praise_only']}.values())
    candidates, stats = [], []
    for trait in config.personality['traits']:
        directions = {d: [r for r in episodes if any(s['trait'] == trait and s['direction'] == d
                      for s in r['trait_signals'])] for d in (1, -1)}
        for direction in (1, -1):
            rows, opposite = directions[direction], directions[-direction]
            sessions = len({(r['source']['kind'], r['source']['session']) for r in rows})
            passed = (len(rows) >= config.threshold('min_evidence_episodes') and
                      sessions >= config.threshold('min_evidence_sessions') and
                      len(opposite) * 3 <= len(rows))
            statistic = {'trait': trait, 'direction': direction, 'episodes': len(rows),
                         'sessions': sessions, 'opposite': len(opposite), 'qualified': passed}
            stats.append(statistic)
            if passed:
                raw = {'trait': trait, 'delta': direction, 'evidence': sorted(r['id'] for r in rows),
                       'counter_evidence': sorted(r['id'] for r in opposite),
                       'reason': 'Consistent directional evidence meets locked thresholds.'}
                candidates.append({**raw, 'id': digest([batch, raw])[:16], 'statistics': statistic})
    return candidates, stats


def validator(candidates):
    schema = deepcopy(REVIEW_SCHEMA)
    items = schema['properties']['reviews']
    items['minItems'] = items['maxItems'] = len(candidates)
    items['items']['properties']['id']['enum'] = [c['id'] for c in candidates]
    # An empty enum is invalid schema; empty batches are never sent to the model.
    if not candidates:
        del items['items']['properties']['id']['enum']
    return Draft202012Validator(schema)


def validate(value, candidates):
    schema = validator(candidates)
    error = next(schema.iter_errors(value), None)
    if error is not None:
        return 'schema_path=' + '/'.join(map(str, error.absolute_schema_path)) + '; validator=' + str(error.validator)
    expected = {c['id'] for c in candidates}
    ids = [r['id'] for r in value['reviews']]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        return 'review_ids_must_match_candidates_exactly'
    return None


def review(config, episodes, candidates, request):
    settings = config.data['reflector']
    user = {'identity': config.lock.get('identity', []), 'principles': config.lock.get('principles', []),
            'candidates': candidates, 'episodes': [
                {key: r[key] for key in ('id', 'summary', 'trait_signals', 'praise_only', 'source')} for r in episodes]}
    text = canonical(user)
    if len(text) > settings['max_input_chars']:
        raise EngineError('reflection_input_limit')
    body = {'model': settings['model'], 'stream': False, 'temperature': settings['temperature'],
            'max_tokens': settings['max_tokens'], 'messages': [
                {'role': 'system', 'content': (ROOT / 'prompts/reflect.txt').read_text(encoding='utf-8')},
                {'role': 'user', 'content': text}]}
    for attempt in range(2):
        value = request(local_endpoint(settings['base_url']), body, settings)
        error = validate(value, candidates)
        if error is None:
            return value
        if attempt:
            raise EngineError('invalid_reflection_response')
        body['messages'].append({'role': 'user', 'content': 'Schema validation failed: ' + error +
            '. Retry once. Return exactly one review per supplied id, only id, decision (approve/veto), reason. '
            'Never return proposals, traits, deltas, evidence, or extra ids.'})
