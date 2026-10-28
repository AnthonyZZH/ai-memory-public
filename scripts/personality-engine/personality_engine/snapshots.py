"""Surgical, byte-preserving snapshot updates with optimistic concurrency."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import yaml

from .policy import EngineError, atomic, inside

FOOTER = re.compile(r'\[persona sha256=[0-9a-f]{8} 字数=\d+\]')


def fingerprint(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    stamp = (before.st_mtime_ns, before.st_size, before.st_ino)
    if stamp != (after.st_mtime_ns, after.st_size, after.st_ino):
        raise EngineError('sync_concurrent_edit')
    return raw, stamp + (hashlib.sha256(raw).hexdigest(),)


def json_strings(text):
    """Map JSON string value paths to raw token bounds, preserving every byte."""
    decoder, spans = json.JSONDecoder(), {}

    def space(i):
        while i < len(text) and text[i].isspace():
            i += 1
        return i

    def value(i, path):
        i = space(i)
        start = i
        if text[i] == '{':
            i = space(i + 1)
            keys = set()
            while text[i] != '}':
                key, i = decoder.raw_decode(text, i)
                if not isinstance(key, str) or key in keys:
                    raise EngineError('sync_ambiguous_json')
                keys.add(key)
                i = space(i)
                if text[i] != ':':
                    raise EngineError('sync_invalid_json')
                i = space(value(i + 1, path + (key,)))
                if text[i] != ',':
                    break
                i = space(i + 1)
            if text[i] != '}':
                raise EngineError('sync_invalid_json')
            return i + 1
        if text[i] == '[':
            i, index = space(i + 1), 0
            while text[i] != ']':
                i = space(value(i, path + (index,)))
                index += 1
                if text[i] != ',':
                    break
                i = space(i + 1)
            if text[i] != ']':
                raise EngineError('sync_invalid_json')
            return i + 1
        item, end = decoder.raw_decode(text, i)
        if isinstance(item, str):
            spans[path] = (start, end)
        return end

    end = space(value(0, ()))
    if end != len(text):
        raise EngineError('sync_invalid_json')
    return spans


def decoded_boundary(text, start, count):
    """Raw JSON offset after count decoded Unicode codepoints (incl surrogates)."""
    i = start + 1
    for _ in range(count):
        if text[i] != '\\':
            i += 1
        elif text[i + 1] != 'u':
            i += 2
        else:
            code = int(text[i + 2:i + 6], 16)
            if 0xD800 <= code <= 0xDBFF and text[i + 6:i + 8] == '\\u' and 0xDC00 <= int(text[i + 8:i + 12], 16) <= 0xDFFF:
                i += 12
            else:
                i += 6
    return i


def managed_end(value, kind):
    expected = '以下为人格与说话方式设定：' if kind == 'lmstudio' else '<persona>\n'
    matches = list(FOOTER.finditer(value))
    if not value.startswith(expected) or len(matches) != 1:
        raise EngineError('sync_unmanaged_prompt')
    return matches[0].end()


def yaml_node(root, path):
    for key in path:
        if isinstance(key, int):
            root = root.value[key]
        else:
            matches = [value for name, value in root.value if name.value == key]
            if len(matches) != 1:
                raise EngineError('sync_ambiguous_yaml')
            root = matches[0]
    return root


def preset_paths(value, preset, path=()):
    if isinstance(value, dict):
        if value.get('id') == preset and isinstance(value.get('plugins'), list):
            for i, plugin in enumerate(value['plugins']):
                if isinstance(plugin, dict) and plugin.get('id') == 'persona' and isinstance(plugin.get('config', {}).get('prefix'), str):
                    yield path + ('plugins', i, 'config', 'prefix')
        for key, item in value.items():
            yield from preset_paths(item, preset, path + (key,))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from preset_paths(item, preset, path + (i,))


def get(value, path):
    for key in path:
        value = value[key]
    return value


def replace(raw, target, prompt):
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    text = raw[len(bom):].decode('utf-8')
    kind = target['kind']
    data = json.loads(text) if kind == 'lmstudio' else yaml.safe_load(text)
    if kind == 'lmstudio':
        fields = data['operation']['fields']
        paths = [('operation', 'fields', i, 'value') for i, field in enumerate(fields) if field.get('key') == 'llm.prediction.systemPrompt']
        if len(paths) != 1:
            raise EngineError('sync_prompt_field_not_unique')
        path = paths[0]
        old = get(data, path)
        end = managed_end(old, kind)
        start_token, end_token = json_strings(text)[path]
        start = start_token + 1
        stop = decoded_boundary(text, start_token, end)
        replacement = json.dumps(prompt, ensure_ascii=False)[1:-1]
        expected_value = prompt + old[end:]
    elif kind == 'dsh':
        paths = list(preset_paths(data, target['preset']))
        if len(paths) != 1:
            raise EngineError('sync_prompt_field_not_unique')
        path = paths[0]
        old = get(data, path)
        end = managed_end(old, kind)
        if old[end:].strip():
            raise EngineError('sync_unmanaged_dsh_suffix')
        node = yaml_node(yaml.compose(text), path)
        if not isinstance(node, yaml.ScalarNode):
            raise EngineError('sync_invalid_yaml_prefix')
        start, stop = node.start_mark.index, node.end_mark.index
        expected_value = prompt + old[end:]
        if node.style in ('|', '>'):
            # Block scalar end_mark includes the terminal line break.
            replacement = json.dumps(expected_value, ensure_ascii=False) + ('\r\n' if text[:stop].endswith('\r\n') else '\n')
        else:
            replacement = json.dumps(expected_value, ensure_ascii=False)
    else:
        raise EngineError('sync_unknown_target')
    if old == expected_value:
        return raw, {'field': list(path), 'persona_only': True}
    new = text[:start] + replacement + text[stop:]
    parsed = json.loads(new) if kind == 'lmstudio' else yaml.safe_load(new)
    if get(parsed, path) != expected_value:
        raise EngineError('sync_replacement_invalid')
    # Semantic check independent of surgical byte preservation: every other
    # value, including credentials, model selection and library rules is equal.
    parent = parsed
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = old
    if parsed != data:
        raise EngineError('sync_nonpersona_change')
    result = bom + new.encode('utf-8')
    return result, {'field': list(path), 'persona_only': True}


def sync(config, dry_run=False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from persona_loader import load_persona, render_persona
    content = load_persona(config.root / 'her')
    prompts = {kind: render_persona(content, 'local' if kind == 'lmstudio' else 'dsh', config.root / 'her') for kind in ('lmstudio', 'dsh')}
    targets = config.data.get('sync', {}).get('targets', [])
    if not targets:
        raise EngineError('sync_targets_missing')
    plans, seen = [], set()
    for target in targets:
        path = config.resolve(target['path'])
        if path in seen or inside(path, config.root / 'her') or inside(path, config.private):
            raise EngineError('sync_target_not_allowed')
        seen.add(path)
        raw, stamp = fingerprint(path)
        updated, detail = replace(raw, target, prompts[target['kind']])
        plans.append((target, path, raw, stamp, updated, detail))
    changed = [plan for plan in plans if plan[2] != plan[4]]
    result = {'changed': len(changed), 'written': 0, 'dry_run': dry_run,
              'targets': [{'id': p[0]['id'], 'changed': p[2] != p[4], **p[5]} for p in plans]}
    if dry_run or not changed:
        return result
    # Validate ALL inputs before any backup or replacement. Recheck immediately
    # before each atomic replacement, including a touch with unchanged content.
    for _, path, _, stamp, _, _ in plans:
        if fingerprint(path)[1] != stamp:
            raise EngineError('sync_concurrent_edit')
    backup = config.root / 'backups' / ('sync-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    if not inside(backup, config.root / 'backups') or not inside(backup, config.root):
        raise EngineError('sync_backup_path_invalid')
    backup.mkdir(parents=True, exist_ok=False)
    for target, path, raw, _, _, _ in changed:
        if re.fullmatch(r'[a-z0-9-]+', target['id']) is None:
            raise EngineError('sync_target_id_invalid')
        with (backup / (target['id'] + '-' + path.name)).open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for _, path, _, stamp, updated, _ in changed:
        if fingerprint(path)[1] != stamp:
            raise EngineError('sync_concurrent_edit')
        atomic(path, updated)
        if path.read_bytes() != updated:
            raise EngineError('sync_write_verification_failed')
        result['written'] += 1
    result['backup'] = str(backup)
    return result
