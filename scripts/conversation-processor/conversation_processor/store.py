"""Durable cursors, retry queue and canonical outbox; no downstream memory writes."""
import json
import os
from pathlib import Path
import sqlite3
import uuid
from .common import now


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS enabled_sources (
            source_id TEXT PRIMARY KEY, enabled_at_utc TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions (
            source_id TEXT NOT NULL, source_kind TEXT NOT NULL, session_id TEXT NOT NULL,
            file_identity TEXT NOT NULL, enabled_at_utc TEXT NOT NULL,
            baseline_done INTEGER NOT NULL, read_cursor TEXT NOT NULL,
            extracted_cursor TEXT, persona_hash TEXT, last_ref TEXT,
            observed_at TEXT NOT NULL, status TEXT NOT NULL,
            PRIMARY KEY(source_id,session_id));
          CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, session_id TEXT NOT NULL,
            unit_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0, code TEXT, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS outbox (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, code TEXT NOT NULL,
            ref TEXT);
        ''')

    def close(self):
        self.db.close()

    def event(self, code, ref=None):
        self.db.execute('INSERT INTO events(observed_at,code,ref) VALUES (?,?,?)', (now(), code, ref))

    def session(self, source_id, session_id):
        return self.db.execute('SELECT * FROM sessions WHERE source_id=? AND session_id=?',
                               (source_id, session_id)).fetchone()

    def save_session(self, source, snapshot, identity, enabled_at):
        self.db.execute('''INSERT INTO sessions VALUES(?,?,?,?,?,1,?,NULL,?,NULL,?,'ready')
          ON CONFLICT(source_id,session_id) DO UPDATE SET file_identity=excluded.file_identity,
          read_cursor=excluded.read_cursor, observed_at=excluded.observed_at, status='ready' ''',
          (source['id'], source['kind'], snapshot.session, identity, enabled_at,
           json.dumps(snapshot.cursor), source.get('persona_hash'), now()))

    def success_cursor(self, turn, source_id, cursor_session):
        source = turn['source']
        self.db.execute('''UPDATE sessions SET extracted_cursor=?, persona_hash=?, last_ref=?,
                           observed_at=?, status='ready' WHERE source_id=? AND session_id=?''',
                        (json.dumps(source['refs']), turn['persona_hash'], source['refs'][-1], now(),
                         source_id, cursor_session))


def publish(output_dir, candidate_id, payload):
    """Atomic no-overwrite publication; retained staging files support auditing.

    A hard link publishes only a completely fsynced inode. Existing candidates
    must match exactly. No files, including staging files, are deleted.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{candidate_id}.jsonl'
    data = (payload + '\n').encode('utf-8')
    if destination.exists():
        if destination.read_bytes() != data:
            raise ValueError('output_conflict')
        return
    staging = directory / '.staging'
    staging.mkdir(exist_ok=True)
    temp = staging / f'{candidate_id}-{uuid.uuid4().hex}.tmp'
    with temp.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temp, destination)
    except FileExistsError:
        if destination.read_bytes() != data:
            raise ValueError('output_conflict') from None
