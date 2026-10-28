"""Synthetic JSONL turn units for tests and controlled offline simulations."""
from . import Snapshot, read_bytes
from ..common import complete_lines, iso, now


def scan(path, source, cursor, baseline, enabled_at):
    raw = read_bytes(path, source)
    records, offset = complete_lines(raw)
    session = 'file:' + path.name
    floor = offset if baseline else cursor.get('floor', 0)
    skip_partial = offset if baseline and offset < len(raw) else cursor.get('skip_partial_after')
    result = []
    if not baseline:
        previous_end = 0
        for position, value in records:
            line_start, previous_end = previous_end, position
            if position <= floor or line_start == skip_partial:
                continue
            if (value['source']['kind'] != 'sim' or not value['source']['session']
                    or not value['source']['refs'] or not isinstance(value['user'], str)
                    or not isinstance(value['assistant'], str)):
                raise ValueError('invalid_sim_turn')
            value['source']['source_time'] = iso(value['source'].get('source_time'))
            value['source']['observed_at'] = now()
            value.setdefault('persona_hash', None)
            result.append(value)
    return Snapshot(session, {'floor': floor, 'line_offset': offset, 'skip_partial_after': skip_partial}, result)
