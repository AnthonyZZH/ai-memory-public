"""Read-only source adapters. Scanning is replay-based; acceptance is incremental."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Snapshot:
    session: str
    cursor: dict
    turns: list


def files(config, source):
    path = config.resolve(source['path'])
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ValueError('source_not_found')
    return sorted(p for p in path.glob(source['pattern']) if p.is_file())


def scan(kind, path, source, cursor=None, baseline=False, enabled_at=None):
    from . import dsh, lmstudio, cc, sim
    return {'dsh': dsh, 'lmstudio': lmstudio, 'cc': cc, 'sim': sim}[kind].scan(
        Path(path), source, cursor or {}, baseline, enabled_at)


def read_bytes(path, source):
    limit = source.get('max_file_bytes', 67108864)
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('source_too_large')
    return data
