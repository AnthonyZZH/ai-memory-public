"""Metadata-only consumption ledger; private payloads never enter this database."""
import sqlite3
from .policy import EngineError, inside


SCHEMA = '''
CREATE TABLE IF NOT EXISTS consumed (
 id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, sensitivity TEXT NOT NULL,
 payload TEXT, consumed_at TEXT NOT NULL, reflected INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS proposals (
 id TEXT PRIMARY KEY, document TEXT NOT NULL, status TEXT NOT NULL,
 commit_sha TEXT, applied_at TEXT, reverted_at TEXT);
CREATE TABLE IF NOT EXISTS reflections (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_batches (
 id TEXT PRIMARY KEY, document TEXT NOT NULL, status TEXT NOT NULL);
'''


class Store:
    def __init__(self, config, readonly=False):
        self.db = None
        if not inside(config.state, config.cache) or not inside(config.cache, config.root):
            raise EngineError('invalid_state_path')
        if readonly and not config.state.exists():
            self.db = sqlite3.connect(':memory:')
            self.db.executescript(SCHEMA)
        elif readonly:
            self.db = sqlite3.connect(config.state.as_uri() + '?mode=ro', uri=True)
        else:
            config.state.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(config.state)
            self.db.executescript(SCHEMA)
        self.db.row_factory = sqlite3.Row

    def close(self):
        if self.db:
            self.db.close()
