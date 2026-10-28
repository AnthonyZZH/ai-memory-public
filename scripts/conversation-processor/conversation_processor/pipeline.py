"""Explicit baseline, incremental admission, local extraction and outbox publishing."""
import json
from pathlib import Path
import sqlite3
import zstandard
from . import adapters
from .common import candidate_id, digest, now
from .extract import extract, Invalid, Unavailable, validate_unit
from .store import Store, publish
from .locking import exclusive


def find_snapshot(path, source, store, config, enabled_at, baseline=False):
    # Replay metadata to identify session; no cursor is committed before validation.
    initial = adapters.scan(source['kind'], path, source, baseline=True, enabled_at=enabled_at)
    old = store.session(source['id'], initial.session)
    cursor = json.loads(old['read_cursor']) if old else {}
    snapshot = initial if baseline else adapters.scan(source['kind'], path, source, cursor, enabled_at=enabled_at)
    st = path.stat()
    identity = json.dumps({'path': digest(str(path.resolve())), 'device': st.st_dev, 'inode': st.st_ino})
    return snapshot, identity


@exclusive
def baseline(config):
    if not config.sources:
        raise ValueError('no_enabled_sources')
    store = Store(config.resolve(config.data['cursor_db']))
    stamp, count = now(), 0
    try:
        with store.db:
            for source in config.sources:
                if store.db.execute('SELECT 1 FROM enabled_sources WHERE source_id=?', (source['id'],)).fetchone():
                    raise ValueError('baseline_already_registered')
                for path in adapters.files(config, source):
                    snapshot, identity = find_snapshot(path, source, store, config, stamp, True)
                    store.save_session(source, snapshot, identity, stamp)
                    count += 1
                store.db.execute('INSERT INTO enabled_sources VALUES (?,?)', (source['id'], stamp))
            store.event('baseline_registered')
        return {'sessions': count, 'enabled_at_utc': stamp, 'extracted': 0}
    finally:
        store.close()


@exclusive
def collect(config):
    store = Store(config.resolve(config.data['cursor_db']))
    counts = {'queued': 0, 'source_errors': 0, 'sessions': 0}
    try:
        for source in config.sources:
            row = store.db.execute('SELECT enabled_at_utc FROM enabled_sources WHERE source_id=?', (source['id'],)).fetchone()
            if row is None:
                raise ValueError('baseline_required')
            try:
                paths = adapters.files(config, source)
            except (OSError, ValueError):
                with store.db:
                    store.event('source_unavailable', digest(source['id'], 16))
                counts['source_errors'] += 1
                continue
            for path in paths:
                try:
                    snapshot, identity = find_snapshot(path, source, store, config, row['enabled_at_utc'])
                    for turn in snapshot.turns:
                        validate_unit(turn)
                    with store.db:
                        for turn in snapshot.turns:
                            store.db.execute('''INSERT OR IGNORE INTO turns(id,source_id,session_id,unit_json,created_at)
                                              VALUES (?,?,?,?,?)''',
                                             (candidate_id(turn), source['id'], snapshot.session,
                                              json.dumps(turn, ensure_ascii=False), now()))
                            counts['queued'] += store.db.execute('SELECT changes()').fetchone()[0]
                        store.save_session(source, snapshot, identity, row['enabled_at_utc'])
                    counts['sessions'] += 1
                except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError,
                        OverflowError, Invalid, zstandard.ZstdError):
                    with store.db:
                        store.event('source_invalid', digest(str(path), 16))
                    counts['source_errors'] += 1
        return counts
    finally:
        store.close()


def flush_outbox(store, config):
    published = 0
    enabled = {s['id'] for s in config.sources}
    rows = store.db.execute('''SELECT outbox.* FROM outbox JOIN turns USING(id)
                               WHERE published=0 ORDER BY id''').fetchall()
    for row in rows:
        source_id = store.db.execute('SELECT source_id FROM turns WHERE id=?', (row['id'],)).fetchone()[0]
        if source_id not in enabled:
            continue
        try:
            publish(config.resolve(config.data['output_dir']), row['id'], row['payload'])
        except (OSError, ValueError):
            with store.db:
                store.event('output_conflict_or_unavailable', row['id'])
            continue
        with store.db:
            store.db.execute('UPDATE outbox SET published=1 WHERE id=?', (row['id'],))
            turn_row = store.db.execute('SELECT * FROM turns WHERE id=?', (row['id'],)).fetchone()
            store.db.execute("UPDATE turns SET status='emitted' WHERE id=?", (row['id'],))
            store.success_cursor(json.loads(turn_row['unit_json']), turn_row['source_id'], turn_row['session_id'])
        published += 1
    return published


@exclusive
def extract_pending(config, limit=None):
    store = Store(config.resolve(config.data['cursor_db']))
    counts = {'emitted': 0, 'none': 0, 'rejected': 0, 'unavailable': 0}
    try:
        counts['emitted'] += flush_outbox(store, config)
        enabled = {s['id'] for s in config.sources}
        rows = [r for r in store.db.execute("SELECT * FROM turns WHERE status='queued' ORDER BY created_at,id").fetchall()
                if r['source_id'] in enabled]
        for row in rows[:limit] if limit is not None else rows:
            turn = json.loads(row['unit_json'])
            try:
                value = extract(turn, config)
            except Unavailable:
                with store.db:
                    store.db.execute('UPDATE turns SET attempts=attempts+1,code=? WHERE id=?', ('local_unavailable', row['id']))
                    store.event('local_unavailable', row['id'])
                counts['unavailable'] += 1
                break  # No hot retry loop or cloud fallback.
            except Invalid as exc:
                with store.db:
                    store.db.execute("UPDATE turns SET status='rejected',attempts=attempts+1,code=? WHERE id=?", (str(exc), row['id']))
                    store.event(str(exc), row['id'])
                counts['rejected'] += 1
                continue
            with store.db:
                if value['category'] == 'none':
                    store.db.execute("UPDATE turns SET status='none',attempts=attempts+1 WHERE id=?", (row['id'],))
                    store.success_cursor(turn, row['source_id'], row['session_id'])
                    counts['none'] += 1
                else:
                    store.db.execute('INSERT OR IGNORE INTO outbox(id,payload) VALUES (?,?)',
                                     (row['id'], json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))))
                    store.db.execute("UPDATE turns SET status='outbox',attempts=attempts+1 WHERE id=?", (row['id'],))
            counts['emitted'] += flush_outbox(store, config)
        counts['pending'] = sum(r['source_id'] in enabled for r in store.db.execute(
            "SELECT source_id FROM turns WHERE status IN ('queued','outbox')"))
        return counts
    finally:
        store.close()


@exclusive
def status(config):
    store = Store(config.resolve(config.data['cursor_db']))
    try:
        return {'sources': store.db.execute('SELECT count(*) FROM enabled_sources').fetchone()[0],
                'sessions': store.db.execute('SELECT count(*) FROM sessions').fetchone()[0],
                'turns': dict(store.db.execute('SELECT status,count(*) FROM turns GROUP BY status').fetchall())}
    finally:
        store.close()
