"""LM Studio selected-version snapshots. Old slots and version switches are not new turns."""
import json
import re
from ..markers import hashes
from ..expressions import audience
from . import Snapshot, read_bytes
from ..common import after, digest, now, text_blocks, unit


def selected(message):
    versions = message['versions']
    index = message['currentlySelected']
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(versions):
        raise ValueError('invalid_selected_version')
    return versions[index], digest(versions[index])


def visible(version):
    if version.get('role') == 'user' and version.get('type') == 'singleStep':
        return text_blocks(version.get('content')), True
    if version.get('role') != 'assistant' or version.get('type') != 'multiStep':
        return '', False
    texts, ready = [], False
    for step in version.get('steps', []):
        if (step.get('type') in ('toolStatus', 'requestConfirmToolCall') or step.get('roleOverride') == 'tool'
                or any(b.get('type') in ('toolCallRequest', 'toolCallResult') for b in step.get('content', []) if isinstance(b, dict))):
            texts, ready = [], False
            continue
        if (step.get('type') != 'contentBlock' or step.get('roleOverride') == 'tool'
                or (step.get('style') or {}).get('type') == 'thinking'):
            continue
        text = text_blocks(step.get('content'))
        if text:
            texts.append(text)
            ready = isinstance(step.get('genInfo', {}).get('stats'), dict)
    return '\n'.join(texts), ready


def scan(path, source, cursor, baseline, enabled_at):
    before = path.stat()
    data = json.loads(read_bytes(path, source).decode('utf-8-sig'))
    after_stat = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after_stat.st_size, after_stat.st_mtime_ns):
        raise ValueError('unstable_snapshot')
    messages = data.get('messages', [])
    floor = len(messages) if baseline else cursor.get('floor', 0)
    finished = set(cursor.get('finished_slots', []))
    selected_versions = [selected(m) for m in messages]
    next_cursor = {'floor': floor, 'slots': [fingerprint for _, fingerprint in selected_versions],
                   'finished_slots': sorted(finished)}
    session = path.name.removesuffix('.conversation.json')
    if baseline or data.get('preset') not in source['presets']:
        next_cursor['floor'] = max(floor, len(messages))
        return Snapshot(session, next_cursor, [])
    # A newly discovered old snapshot cannot establish post-T0 provenance.
    if not cursor and not after(data.get('createdAt'), enabled_at):
        next_cursor['floor'] = len(messages)
        return Snapshot(session, next_cursor, [])
    matches = hashes(data.get('systemPrompt', ''), source)
    persona = matches[-1] if matches else source.get('persona_hash')
    if source.get('require_persona_marker', False) and not matches:
        next_cursor['floor'] = max(floor, len(messages))
        return Snapshot(session, next_cursor, [])
    turns, pending = [], None
    for slot, (version, fingerprint) in enumerate(selected_versions):
        role = version.get('role')
        text, ready = visible(version)
        if role == 'user':
            pending = (slot, text, fingerprint, audience(version, data, source))
        elif role == 'assistant' and pending and text and ready:
            user_slot, user, user_fingerprint, scope = pending
            if user and user_slot >= floor and slot not in finished:
                refs = [f'slot:{user_slot}:version:{user_fingerprint}', f'slot:{slot}:version:{fingerprint}']
                turns.append(unit('lmstudio', session, refs, user, text, persona, None, scope))
                finished.add(slot)
            pending = None
    next_cursor['finished_slots'] = sorted(finished)
    return Snapshot(session, next_cursor, turns)
