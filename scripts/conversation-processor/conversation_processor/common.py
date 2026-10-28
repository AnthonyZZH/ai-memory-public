"""Protocol primitives. Contents are never interpolated into diagnostic output."""
from datetime import datetime, timezone
import hashlib
import json


def now():
    return datetime.now(timezone.utc).isoformat()


def iso(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    if not isinstance(value, str):
        raise ValueError('invalid_time')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timezone_required')
    return dt.astimezone(timezone.utc).isoformat()


def digest(value, length=64):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()[:length]


def candidate_id(unit):
    source = unit['source']
    return digest([source['kind'], source['session'], source['refs']], 16)


def unit(kind, session, refs, user, assistant, persona_hash=None, source_time=None, audience=None):
    result = {'source': {'kind': kind, 'session': session, 'refs': refs,
                       'source_time': iso(source_time), 'observed_at': now()},
            'persona_hash': persona_hash, 'user': user, 'assistant': assistant}
    if audience is not None:
        result['source']['audience'] = audience
    return result


def text_blocks(blocks):
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ''
    return '\n'.join(b['text'] for b in blocks if isinstance(b, dict)
                     and b.get('type') == 'text' and isinstance(b.get('text'), str))


def complete_lines(raw):
    """Only newline-terminated records are committed; never consume a torn tail."""
    end = raw.rfind(b'\n') + 1
    records = []
    offset = 0
    for line in raw[:end].splitlines(keepends=True):
        offset += len(line)
        if line.strip():
            records.append((offset, json.loads(line.decode('utf-8-sig'))))
    return records, end


def after(value, boundary):
    return value is not None and iso(value) >= iso(boundary)
