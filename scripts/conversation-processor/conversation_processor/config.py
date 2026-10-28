"""All deployment-specific identities, locations, traits and policy live in YAML."""
from dataclasses import dataclass
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit
import yaml


@dataclass
class Config:
    path: Path
    data: dict

    def resolve(self, value):
        p = Path(value).expanduser()
        return (self.path.parent / p).resolve() if not p.is_absolute() else p.resolve()

    @property
    def sources(self):
        return [s for s in self.data['sources'] if s.get('enabled', True)]


def local_endpoint(value):
    """Literal loopback only; localhost is rewritten to avoid DNS ambiguity."""
    p = urlsplit(value)
    if (p.scheme != 'http' or not p.hostname or p.username is not None
            or p.password is not None or p.query or p.fragment):
        raise ValueError('loopback_http_required')
    hostname = p.hostname
    if hostname == 'localhost':
        hostname = '127.0.0.1'
    if not ipaddress.ip_address(hostname).is_loopback:
        raise ValueError('loopback_required')
    host = f'[{hostname}]' if ':' in hostname else hostname
    port = f':{p.port}' if p.port is not None else ''
    return f'http://{host}{port}{p.path.rstrip("/")}/chat/completions'


def load(path):
    p = Path(path).resolve()
    data = yaml.safe_load(p.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('unsupported_config')
    for key in ('cursor_db', 'output_dir', 'sources', 'extractor', 'traits', 'sensitivity'):
        if key not in data:
            raise ValueError('incomplete_config')
    if not all(isinstance(data[k], str) and data[k] for k in ('cursor_db', 'output_dir')):
        raise ValueError('invalid_paths')
    if not isinstance(data['traits'], list) or any(not isinstance(t, str) or not t for t in data['traits']):
        raise ValueError('invalid_traits')
    if len(data['traits']) != len(set(data['traits'])):
        raise ValueError('duplicate_traits')
    e = data['extractor']
    local_endpoint(e['base_url'])
    if not isinstance(e.get('model'), str) or not e['model'].strip():
        raise ValueError('model_required')
    for k in ('timeout_seconds', 'max_response_bytes', 'max_turn_chars', 'max_tokens'):
        if not isinstance(e.get(k), (int, float)) or e[k] <= 0:
            raise ValueError('invalid_extractor_limit')
    if not isinstance(e.get('temperature'), (int, float)) or not 0 <= e['temperature'] <= 2:
        raise ValueError('invalid_temperature')
    policy = data['sensitivity']
    if policy.get('keyword_level') not in ('private', 'unsure'):
        raise ValueError('strict_keyword_level_required')
    if not isinstance(policy.get('keywords'), dict):
        raise ValueError('sensitive_keywords_required')
    if not set(policy['keywords']) <= {'health', 'body', 'finance', 'birthday', 'home_location', 'other'}:
        raise ValueError('unknown_sensitive_tag')
    if any(not isinstance(words, list) or any(not isinstance(w, str) or not w for w in words)
           for words in policy['keywords'].values()):
        raise ValueError('invalid_keywords')
    seen = set()
    expressions = data.get('expressions', {})
    if (not isinstance(expressions, dict) or not set(expressions) <= {'non_owner_markers', 'aggressive_keywords'}
            or any(not isinstance(words, list) or any(not isinstance(w, str) or not w.strip() for w in words)
                   for words in expressions.values())):
        raise ValueError('invalid_expression_policy')
    praise = data.get('praise', {})
    if not isinstance(praise, dict) or not set(praise) <= {'keywords', 'trait_aliases'}:
        raise ValueError('invalid_praise_policy')
    words, aliases = praise.get('keywords', []), praise.get('trait_aliases', {})
    if (not isinstance(words, list) or any(not isinstance(w, str) or not w.strip() for w in words)
            or not isinstance(aliases, dict) or not set(aliases) <= set(data['traits'])
            or any(not isinstance(names, list) or any(not isinstance(n, str) or not n.strip() for n in names)
                   for names in aliases.values())):
        raise ValueError('invalid_praise_policy')
    if not isinstance(data['sources'], list):
        raise ValueError('invalid_sources')
    for s in data['sources']:
        if s['kind'] not in ('dsh', 'lmstudio', 'cc', 'sim') or not isinstance(s['id'], str) or s['id'] in seen:
            raise ValueError('invalid_source')
        seen.add(s['id'])
        if not isinstance(s.get('path'), str) or not s['path']:
            raise ValueError('source_path_required')
        if not isinstance(s.get('pattern'), str) or not s['pattern'] or not isinstance(s.get('enabled', True), bool):
            raise ValueError('invalid_source_selector')
        if s['kind'] == 'dsh' and not s.get('preset'):
            raise ValueError('preset_required')
        if s['kind'] == 'dsh':
            window = s.get('max_window_size', 1 << 31)
            if type(window) is not int or not 1024 <= window <= 1 << 31:
                raise ValueError('invalid_max_window_size')
        if s['kind'] == 'lmstudio' and (not isinstance(s.get('presets'), list) or not s['presets']):
            raise ValueError('presets_required')
        if s['kind'] == 'cc' and (not s.get('cwd') or not isinstance(s.get('models'), list) or not s['models']):
            raise ValueError('cc_identity_required')
    config = Config(p, data)
    for s in data['sources']:
        source_path = config.resolve(s['path'])
        if any(config.resolve(data[key]).is_relative_to(source_path) for key in ('cursor_db', 'output_dir')):
            raise ValueError('state_must_not_be_a_source')
    return config
