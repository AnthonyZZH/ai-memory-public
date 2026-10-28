"""Claude Code main-branch, human-only rounds with effective prompt provenance."""
import json
import ntpath
import re
from . import Snapshot, read_bytes
from ..common import after, complete_lines, text_blocks, unit
from ..markers import hashes
from ..expressions import audience


def scan(path, source, cursor, baseline, enabled_at):
    raw = read_bytes(path, source)
    records, offset = complete_lines(raw)
    session_ids = {r['sessionId'] for _, r in records if r.get('sessionId')}
    if len(session_ids) > 1:
        raise ValueError('mixed_sessions')
    session = next(iter(session_ids), path.stem)
    floor = offset if baseline else cursor.get('floor', 0)
    skip_partial = offset if baseline and offset < len(raw) else cursor.get('skip_partial_after')
    next_cursor = {'floor': floor, 'line_offset': offset, 'skip_partial_after': skip_partial,
                   'last_uuid': next((r['uuid'] for _, r in reversed(records) if r.get('uuid')), None)}
    if baseline:
        return Snapshot(session, next_cursor, [])
    nodes = {r['uuid']: r for _, r in records if r.get('type') in ('user', 'assistant')
             and r.get('uuid') and not r.get('isSidechain')}
    leaf = next((r['uuid'] for _, r in reversed(records) if r.get('uuid') in nodes), None)
    branch = set()
    while leaf is not None and leaf in nodes:
        if leaf in branch:
            raise ValueError('cyclic_branch')
        branch.add(leaf)
        leaf = nodes[leaf].get('parentUuid')
    effective = None
    pending, groups, turns = None, {}, []

    def finish():
        if not pending or not pending['eligible']:
            return
        final = next((g for g in reversed(list(groups.values())) if g['text'] and g['end'] and not g['tool']), None)
        if final and final['persona'] and final['model_ok']:
            turns.append(unit('cc', session, [pending['ref'], 'message:' + final['id']], pending['text'],
                              final['text'], final['persona'], pending['time'], pending['audience']))

    seen_nodes = set()
    previous_end = 0
    for position, row in records:
        line_start, previous_end = previous_end, position
        attachment = row.get('attachment', {})
        if row.get('type') == 'attachment' and attachment.get('type') == 'prompt_snapshot':
            matches = hashes(json.dumps(attachment.get('systemPrompt'), ensure_ascii=False), source)
            effective = matches[-1] if matches else None
        if row.get('uuid') not in branch or row.get('isMeta') or row.get('isSidechain'):
            continue
        if row['uuid'] in seen_nodes:
            continue
        seen_nodes.add(row['uuid'])
        if ntpath.normcase(ntpath.normpath(row.get('cwd', ''))) != ntpath.normcase(ntpath.normpath(source['cwd'])):
            continue
        message, typ = row.get('message', {}), row.get('type')
        blocks = message.get('content', [])
        if typ == 'user':
            if message.get('role') != 'user' or line_start == skip_partial:
                continue
            # A mixed tool_result carrier is not an independent human message.
            if isinstance(blocks, list) and any(b.get('type') == 'tool_result' for b in blocks if isinstance(b, dict)):
                continue
            if row.get('turnOrigin') not in (None, 'human'):
                continue
            text = text_blocks(blocks)
            if not text:
                continue
            finish()
            pending = {'text': text, 'ref': 'uuid:' + row['uuid'], 'time': row.get('timestamp'),
                       'audience': audience(row, row.get('source'), message, source),
                       'eligible': position > floor and after(row.get('timestamp'), enabled_at)}
            groups = {}
        elif typ == 'assistant' and pending:
            if message.get('role') != 'assistant':
                continue
            message_id = message.get('id')
            if not message_id:
                continue
            group = groups.setdefault(message_id, {'id': message_id, 'text': '', 'refs': [], 'end': False,
                                                     'tool': False, 'model_ok': True, 'persona': effective})
            group['refs'].append('uuid:' + row['uuid'])
            group['model_ok'] &= message.get('model') in source['models'] and row.get('requestedModel', message.get('model')) in source['models']
            group['persona'] = effective
            group['tool'] |= isinstance(blocks, list) and any(b.get('type') == 'tool_use' for b in blocks if isinstance(b, dict))
            group['end'] |= message.get('stop_reason') == 'end_turn'
            text = text_blocks(blocks)
            if text and text != group['text']:
                if text.startswith(group['text']):
                    group['text'] = text
                elif not group['text'].startswith(text):
                    group['text'] += text
    finish()
    return Snapshot(session, next_cursor, turns)
