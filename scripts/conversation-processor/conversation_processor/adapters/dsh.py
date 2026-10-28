"""DSH v4 committed event frames, preset timeline and completed human turns."""
import json
import re
import zstandard
from . import Snapshot, read_bytes
from ..common import after, complete_lines, text_blocks, unit
from ..markers import hashes
from ..expressions import audience


DEFAULT_MAX_WINDOW_SIZE = 1 << 31  # Bytes, bounded at 2 GiB; not a preallocation.


def frames(raw, with_offsets=False, max_window_size=DEFAULT_MAX_WINDOW_SIZE, statistics=None):
    """Return only complete checksum-validated concatenated frames and offset."""
    if type(max_window_size) is not int or not 1024 <= max_window_size <= DEFAULT_MAX_WINDOW_SIZE:
        raise ValueError('invalid_max_window_size')
    remaining = raw
    offset = 0
    rows = []
    starts = []
    if statistics is not None:
        statistics.update(frames=0, records=0, max_declared_window_bytes=0, incomplete_tail_bytes=0)
    while remaining:
        decoder = zstandard.ZstdDecompressor(max_window_size=max_window_size).decompressobj()
        decoded = decoder.decompress(remaining)
        if not decoder.eof:
            break
        consumed = len(remaining) - len(decoder.unused_data)
        if consumed <= 0 or len(decoded) > 67108864:
            raise ValueError('invalid_frame')
        items, end = complete_lines(decoded)
        if end != len(decoded):
            raise ValueError('noncanonical_frame')
        if statistics is not None:
            statistics['frames'] += 1
            statistics['records'] += len(items)
            statistics['max_declared_window_bytes'] = max(
                statistics['max_declared_window_bytes'], zstandard.get_frame_parameters(remaining).window_size)
        rows.extend(item for _, item in items)
        starts.extend([offset] * len(items))
        offset += consumed
        remaining = decoder.unused_data
    if statistics is not None:
        statistics['incomplete_tail_bytes'] = len(raw) - offset
    return (rows, offset, starts) if with_offsets else (rows, offset)


def scan(path, source, cursor, baseline, enabled_at):
    raw = read_bytes(path, source)
    rows, offset, frame_starts = frames(raw, True, source.get('max_window_size', DEFAULT_MAX_WINDOW_SIZE))
    if not rows or rows[0].get('type') != 'session' or rows[0].get('version') != 4:
        raise ValueError('unsupported_session')
    header, events = rows[0], rows[1:]
    session = header['id']
    seqs = [e['seq'] for e in events]
    if any(not isinstance(seq, int) for seq in seqs) or seqs != sorted(set(seqs)):
        raise ValueError('invalid_sequence')
    floor = max(seqs, default=-1) if baseline else cursor.get('floor', -1)
    skip_frame = offset if baseline and offset < len(raw) else cursor.get('skip_baseline_frame')
    next_cursor = {'floor': floor, 'seq': max(seqs, default=-1), 'frame_offset': offset,
                   'skip_baseline_frame': skip_frame}
    if baseline:
        return Snapshot(session, next_cursor, [])
    inherited = header.get('seedLength', header.get('inheritedEventCount', 0))
    if header.get('isSeeded') and not ('seedLength' in header or 'inheritedEventCount' in header):
        return Snapshot(session, next_cursor, [])
    replaced = []
    for event in events:
        op = event.get('surfaceOp')
        if isinstance(op, dict) and op.get('op', op.get('type')) == 'replace':
            replaced.append((op['startSeq'], op['endSeq']))
    selected = header.get('agentPreset')
    persona = source.get('persona_hash')
    pending = None
    turns = []
    for event, frame_start in zip(events, frame_starts[1:]):
        typ, data, seq = event['type'], event.get('data', {}), event['seq']
        if typ == 'agent-preset/selected':
            selected = data.get('agentPreset')
            pending = None
        elif typ == 'request/context' and 'systemPromptUpdate' in data:
            found = hashes(json.dumps(data['systemPromptUpdate'], ensure_ascii=False), source)
            if found:
                persona = found[-1]
        if seq < inherited or frame_start == skip_frame or any(start <= seq < end for start, end in replaced):
            continue
        if typ == 'turn/start' and pending and pending.get('turn') is not None and pending['turn'] != data.get('turn'):
            pending = None
        if typ == 'user/message' and data.get('source', {}).get('kind') == 'user':
            user = text_blocks(data.get('content'))
            pending = {'user': user, 'user_seq': seq, 'time': event.get('time'),
                       'audience': audience(data.get('source'), data, header, source),
                       'eligible': selected == source['preset'] and seq > floor
                       and after(event.get('time'), enabled_at), 'assistant': '',
                       'refs': [f'seq:{seq}'], 'turn': None}
        elif typ == 'turn/start' and pending:
            pending['turn'] = data.get('turn')
        elif typ == 'assistant/message' and pending:
            if data.get('turn') is not None and pending['turn'] is not None and data['turn'] != pending['turn']:
                continue
            message = data.get('message', {})
            if message.get('role') != 'assistant':
                continue
            blocks = message.get('content', [])
            text = text_blocks(blocks)
            # Tool-call preambles are not the final visible response.
            if text and not any(b.get('type') == 'tool-call' for b in blocks if isinstance(b, dict)):
                pending['assistant'] = text
                pending['refs'] = [pending['refs'][0], f'seq:{seq}']
        elif typ == 'turn/end' and pending:
            if (pending['eligible'] and seq > cursor.get('seq', -1)
                    and selected == source['preset'] and pending['user']
                    and (pending['turn'] is None or data.get('turn') == pending['turn'])
                    and pending['assistant'] and data.get('reason') not in ('error', 'aborted', 'interrupted', 'cancelled')):
                turns.append(unit('dsh', session, [*pending['refs'], f'seq:{seq}'],
                                  pending['user'], pending['assistant'], persona, pending['time'], pending['audience']))
            pending = None
    return Snapshot(session, next_cursor, turns)
