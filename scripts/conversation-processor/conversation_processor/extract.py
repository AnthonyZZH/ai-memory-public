"""Local-only extraction, schema validation, grounding and monotone privacy guard."""
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from http.client import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from .common import candidate_id, iso
from .config import local_endpoint
from .expressions import expression_allowed


ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / 'schema.json').read_text(encoding='utf-8'))
FORMATS = FormatChecker()


@FORMATS.checks('date-time', raises=(ValueError, TypeError, OverflowError))
def datetime_format(value):
    if not isinstance(value, str):
        return True  # The schema's type constraint handles nonstrings.
    return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value)) and iso(value) is not None


VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMATS)
FIELDS = set(SCHEMA['properties']) - {'schema', 'id', 'source', 'persona_hash'}
PROMPT = (ROOT / 'prompts/extract.txt').read_text(encoding='utf-8')


class Unavailable(Exception):
    pass


class Invalid(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.detail = detail or code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_unit(value):
    if not isinstance(value, dict) or set(value) != {'source', 'persona_hash', 'user', 'assistant'}:
        raise Invalid('unit_shape')
    for field in ('source', 'persona_hash'):
        validator = Draft202012Validator(SCHEMA['properties'][field], format_checker=FORMATS)
        if not validator.is_valid(value[field]):
            raise Invalid('unit_metadata')
    if not all(isinstance(value[k], str) and value[k].strip() for k in ('user', 'assistant')):
        raise Invalid('empty_turn')


def sensitive_guard(candidate, turn, policy):
    """Never lower model sensitivity; keywords/tags may only increase it."""
    result = deepcopy(candidate)
    ranks = {'normal': 0, 'unsure': 1, 'private': 2}
    haystack = (turn['user'] + '\n' + turn['assistant'] + '\n' +
                json.dumps({k: result[k] for k in FIELDS}, ensure_ascii=False)).casefold()
    tags = set(result['sensitivity_tags'])
    hit = False
    for tag, keywords in policy['keywords'].items():
        if any(word.casefold() in haystack for word in keywords):
            tags.add(tag)
            hit = True
    level = result['sensitivity']
    if tags and level == 'normal':
        level = 'private'
    if hit and ranks[policy['keyword_level']] > ranks[level]:
        level = policy['keyword_level']
    result['sensitivity'] = level
    result['sensitivity_tags'] = sorted(tags)
    return result


def praise_guard(value, turn, policy):
    """Conservatively mark the whole episode; never clear a model praise flag."""
    result = deepcopy(value)
    text = turn['user'].casefold()
    if any(word.casefold() in text for word in policy.get('keywords', [])):
        aliases = policy.get('trait_aliases', {})
        for signal in result['trait_signals']:
            names = [signal['trait'], *aliases.get(signal['trait'], [])]
            if signal['direction'] == 1 and any(name.casefold() in text for name in names):
                result['praise_only'] = True
                break
    return result


def candidate(turn, payload, config):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise Invalid('payload_fields')
    value = {'schema': 'memory-candidate/v1', 'id': candidate_id(turn),
             'source': deepcopy(turn['source']), 'persona_hash': turn['persona_hash'], **payload}
    error = next(VALIDATOR.iter_errors(value), None)
    if error is not None:
        # Schema paths/validator names only: messages/instances can leak content.
        raise Invalid('schema', 'schema_path=' + '/'.join(map(str, error.absolute_schema_path)) +
                      '; validator=' + str(error.validator))
    if any(signal['trait'] not in config.data['traits'] for signal in value['trait_signals']):
        raise Invalid('unknown_trait')
    traits = [s['trait'] for s in value['trait_signals']]
    if len(set(traits)) != len(traits):
        raise Invalid('duplicate_trait')
    if value['category'] == 'expression' and not expression_allowed(value, config.data.get('expressions', {}), turn['user']):
        raise Invalid('expression_scope')
    for quote in value['quotes']:
        original = turn['user'] if quote['speaker'] == 'owner' else turn['assistant']
        if quote['text'] not in original or len(re.findall(r'[^。！？.!?]+(?:[。！？.!?]+|$)', quote['text'])) > 2:
            raise Invalid('ungrounded_quote')
    if value['expression'] is not None and value['expression'] not in turn['assistant']:
        raise Invalid('ungrounded_expression')
    value = sensitive_guard(value, turn, config.data['sensitivity'])
    value = praise_guard(value, turn, config.data.get('praise', {}))
    if not VALIDATOR.is_valid(value):
        raise Invalid('post_guard_schema')
    return value


def extract(turn, config):
    validate_unit(turn)
    settings = config.data['extractor']
    if len(turn['user']) + len(turn['assistant']) > settings['max_turn_chars']:
        raise Invalid('turn_limit')
    body = {'model': settings['model'], 'stream': False,
            'temperature': settings['temperature'], 'max_tokens': settings['max_tokens'],
            'messages': [{'role': 'system', 'content': PROMPT + '\nallowed_traits=' + json.dumps(config.data['traits'], ensure_ascii=False)},
                         {'role': 'user', 'content': json.dumps({'user': turn['user'], 'assistant': turn['assistant']}, ensure_ascii=False)}]}
    for attempt in range(2):
        payload = request_payload(body, settings)
        try:
            return candidate(turn, payload, config)
        except Invalid as exc:
            if attempt or str(exc) not in ('schema', 'payload_fields'):
                raise
            # Repeat the original task with a safe error explanation. No rejected
            # response or untrusted schema instance is promoted to instructions.
            body['messages'].append({'role': 'user', 'content':
                'The previous response failed JSON Schema validation: ' + exc.detail +
                '. Retry once with every required field and correct types. '
                'expression must be an exact assistant substring string for category=expression; '
                'otherwise null. Never an object. Return a complete JSON object only.'})


def request_payload(body, settings):
    request = Request(local_endpoint(settings['base_url']),
                      json.dumps(body, ensure_ascii=False).encode('utf-8'),
                      {'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=settings['timeout_seconds']) as response:
            raw = response.read(settings['max_response_bytes'] + 1)
        if len(raw) > settings['max_response_bytes']:
            raise Invalid('response_limit')
    except (HTTPError, URLError, OSError, HTTPException) as exc:
        if isinstance(exc, HTTPError):
            exc.close()
        raise Unavailable('local_unavailable') from None
    try:
        data = json.loads(raw)
        choice = data['choices'][0]
        if choice.get('finish_reason') in ('length', 'tool_calls', 'content_filter'):
            raise Invalid('unfinished_response')
        text = choice['message']['content']
        if not isinstance(text, str):
            raise Invalid('nontext_response')
        # Accept a single JSON fence, never extract arbitrary embedded JSON.
        if text.strip().startswith('```json') and text.strip().endswith('```'):
            text = text.strip()[7:-3].strip()
        payload = json.loads(text)
    except (ValueError, KeyError, IndexError, TypeError):
        raise Invalid('invalid_json') from None
    return payload
