"""Configuration, fail-closed write boundary and durable atomic writes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

import yaml


class EngineError(Exception):
    """Messages are fixed codes only: never interpolate candidate/model text."""


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def inside(path, root):
    return path.resolve().is_relative_to(root.resolve())


def atomic(path, data):
    """Caller authorizes path first; temporary files remain in the same directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('xb') as stream:
        stream.write(data if isinstance(data, bytes) else data.encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class Config:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data = yaml.safe_load(self.path.read_text(encoding='utf-8'))
        if not isinstance(self.data, dict) or self.data.get('version') != 1:
            raise EngineError('invalid_config')
        self.root = self.resolve(self.data['repository'])
        self.private = self.resolve(self.data['private_repository'])
        if inside(self.root, self.private) or inside(self.private, self.root):
            raise EngineError('repositories_must_be_separate')
        self.cache = self.root / 'cache/engine'
        self.private_cache = self.private / 'cache/engine'
        if self.cache.resolve() != self.cache or self.private_cache.resolve() != self.private_cache:
            raise EngineError('operational_directory_alias')
        self.state = self.cache / 'state.sqlite'
        self.lock_path = self.root / 'her/identity-lock.yaml'
        self.lock = yaml.safe_load(self.lock_path.read_text(encoding='utf-8'))
        self.rules = self.lock['evolution']
        self.policy_fingerprint = digest(self.lock)
        self.personality_path = self.root / 'her/personality.json'
        self.personality = json.loads(self.personality_path.read_text(encoding='utf-8'))
        for name, trait in self.personality['traits'].items():
            if not isinstance(name, str) or not name or type(trait['value']) is not int:
                raise EngineError('invalid_personality')
            lo, hi = trait['range']
            if type(lo) is not int or type(hi) is not int or lo > hi:
                raise EngineError('invalid_personality_range')
        for key in ('max_step_per_trait', 'monthly_drift_needs_approval'):
            self.threshold(key)
        for key in ('locked_files', 'writable_by_engine'):
            if not isinstance(self.rules.get(key), list) or not self.rules[key]:
                raise EngineError('invalid_write_policy')
            for item in self.rules[key]:
                self._relative(item)
        # Required fixed targets cannot disappear from owner protection.
        for rel in ('her/persona.md', 'her/voice.md', 'her/identity-lock.yaml'):
            if rel not in self.rules['locked_files']:
                raise EngineError('missing_identity_protection')
        for key in ('reflect_every', 'expression_limit', 'max_candidate_bytes', 'max_reflection_episodes'):
            if type(self.data.get(key)) is not int or self.data[key] <= 0:
                raise EngineError('invalid_config_threshold')
        if self.data['max_reflection_episodes'] < self.data['reflect_every']:
            raise EngineError('reflection_batch_smaller_than_trigger')
        from conversation_processor.config import local_endpoint
        settings = self.data['reflector']
        local_endpoint(settings['base_url'])
        if not isinstance(settings.get('model'), str) or not settings['model'].strip():
            raise EngineError('reflection_model_required')
        for key in ('timeout_seconds', 'max_tokens', 'max_response_bytes', 'max_input_chars'):
            if type(settings.get(key)) is not int or settings[key] <= 0:
                raise EngineError('invalid_reflector_limit')
        if type(settings.get('temperature')) not in (int, float) or not 0 <= settings['temperature'] <= 2:
            raise EngineError('invalid_reflector_temperature')

    def resolve(self, value):
        return (self.path.parent / value).resolve()

    @staticmethod
    def _relative(rel):
        if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel:
            raise EngineError('invalid_policy_path')
        if Path(rel).is_absolute() or '..' in Path(rel).parts or '.' == rel:
            raise EngineError('invalid_policy_path')
        return rel

    def threshold(self, name):
        value = self.rules.get(name)
        if type(value) is not int or value <= 0:
            raise EngineError('lock_missing_or_invalid_' + name)
        return value

    def assert_policy_current(self):
        if digest(yaml.safe_load(self.lock_path.read_text(encoding='utf-8'))) != self.policy_fingerprint:
            raise EngineError('identity_lock_changed')

    def authorize(self, path):
        """Resolve junctions/symlinks, check deny first, then exact/directory grants."""
        self.assert_policy_current()
        path = Path(path).resolve()
        root = self.root if inside(path, self.root) else self.private if inside(path, self.private) else None
        if root is None:
            raise EngineError('write_outside_repository')
        rel = path.relative_to(root).as_posix()
        # Private repository gets ONLY mirrored episode writes, never public aggregates.
        if root == self.private and not rel.startswith('her/episodes/'):
            raise EngineError('private_write_outside_episodes')
        for locked in self.rules['locked_files']:
            if path == (root / locked).resolve() or rel.casefold() == locked.rstrip('/').casefold():
                raise EngineError('locked_file_write')
        for grant in self.rules['writable_by_engine']:
            allowed = (root / grant).resolve()
            if (grant.endswith('/') and inside(path, allowed) and path != allowed) or (not grant.endswith('/') and path == allowed):
                if not inside(allowed, root):
                    raise EngineError('write_grant_escaped_repository')
                return root, rel
        raise EngineError('write_not_whitelisted')

    def write(self, path, data):
        self.authorize(path)
        atomic(path, data)

    def operational(self, path, data, private=False):
        root = self.private_cache if private else self.cache
        path = Path(path).resolve()
        if not inside(path, root) or not inside(root, self.private if private else self.root):
            raise EngineError('invalid_operational_path')
        atomic(path, data)


@contextmanager
def exclusive(config, dry_run=False):
    if dry_run:
        yield
        return
    from conversation_processor.locking import acquire
    if not inside(config.cache, config.root) or not inside(config.cache / 'engine.mutex', config.cache):
        raise EngineError('invalid_operational_path')
    with acquire(config.cache / 'engine.mutex'):
        yield


def safe_id(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{16}', value) is None:
        raise EngineError('invalid_id')
    return value
