"""Candidate routing, local reflection, hard guards and bounded evolution."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unicodedata
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from http.client import HTTPException

from jsonschema import Draft202012Validator
import yaml

from conversation_processor import pipeline
from conversation_processor.common import candidate_id
from conversation_processor.config import load as processor_load, local_endpoint
from conversation_processor.extract import VALIDATOR as CANDIDATES, NoRedirect, sensitive_guard
from conversation_processor.expressions import expression_allowed

from . import gitops, notify, reflection
from .policy import EngineError, canonical, digest, now, safe_id
from .store import Store

ROOT = Path(__file__).resolve().parent
PROPOSALS = Draft202012Validator(json.loads((ROOT / 'proposal.schema.json').read_text(encoding='utf-8')))


def processor_config(config):
    return processor_load(config.resolve(config.data['processor_config']))


def heading(text):
    return ' '.join(text.splitlines())


def note(value, private):
    metadata = {'title': heading(value['summary']), 'type': 'note',
                'tags': ['episode', value['category']], 'visibility': 'private' if private else 'her',
                'id': value['id'], 'source': value['source'], 'persona_hash': value['persona_hash'],
                'praise_only': value['praise_only'], 'trait_signals': value['trait_signals']}
    lines = ['---', yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip(), '---',
             '', '## Observations', '', '- [情景] ' + heading(value['summary'])]
    for quote in value['quotes']:
        lines.append('- [' + quote['speaker'] + '] ' + heading(quote['text']))
    lines += ['', '## Relations', '']
    return '\n'.join(lines) + '\n'


def read_text(path):
    return path.read_text(encoding='utf-8') if path.exists() else ''


def expression_changes(config, value=None):
    path = config.root / 'her/evolution/expressions.md'
    config.authorize(path)
    old = read_text(path)
    if old:
        parts = old.split('---', 2)
        if len(parts) != 3 or parts[0].strip():
            raise EngineError('invalid_expressions_file')
        metadata = yaml.safe_load(parts[1])
        entries = metadata.get('entries')
        if not isinstance(entries, list):
            raise EngineError('invalid_expressions_file')
    else:
        entries = []
    policy = processor_config(config).data.get('expressions', {})
    # Legacy entries lack audience provenance. They cannot prove owner-only use;
    # conservatively remove them on rewrite, without deleting any file.
    entries = [e for e in entries if e.get('audience') == 'owner' and expression_allowed(
        {'source': {'audience': e['audience']}, 'expression': e['text']}, policy)]
    if value is not None and expression_allowed(value, policy):
        text = ' '.join(unicodedata.normalize('NFKC', value['expression']).split())
        key = digest(text.casefold())
        stamp = datetime.fromisoformat(value['source']['observed_at'].replace('Z', '+00:00')).astimezone(timezone.utc).isoformat()
        found = False
        for entry in entries:
            if entry['key'] == key:
                entry['last_seen'] = max(entry['last_seen'], stamp)
                found = True
        if not found:
            entries.append({'key': key, 'text': heading(value['expression']), 'last_seen': stamp,
                            'audience': 'owner', 'episode_id': value['id']})
    entries = sorted(entries, key=lambda e: (e['last_seen'], e['key']), reverse=True)[:config.data['expression_limit']]
    metadata = {'title': '常用表达随互动整理', 'type': 'note', 'visibility': 'her', 'entries': entries}
    output = '---\n' + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + '---\n\n## Observations\n\n'
    output += '\n'.join('- ' + e['text'] for e in entries) + '\n\n## Relations\n'
    return output


def route(config, value):
    private = value['sensitivity'] != 'normal'
    root = config.private if private else config.root
    stamp = value['source']['source_time'] or value['source']['observed_at']
    month = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone.utc).strftime('%Y-%m')
    rel = 'her/episodes/' + month + '/' + safe_id(value['id']) + '.md'
    changes = {rel: note(value, private)}
    if not private and value['category'] == 'relationship':
        target = config.root / 'her/relationship.md'
        config.authorize(target)
        text = read_text(target)
        marker = '<!-- episode:' + value['id'] + ' -->'
        if marker not in text:
            if not text:
                text = '---\ntitle: 相处习惯由互动逐步积累\ntype: note\nvisibility: her\n---\n\n## Observations\n\n## Relations\n'
            line = '\n- [关系] ' + heading(value['summary']) + ' ' + marker + '\n'
            if '\n## Relations' in text:
                text = text.replace('\n## Relations', line + '\n## Relations', 1)
            else:
                text += line + '\n## Relations\n'
        changes['her/relationship.md'] = text
    elif not private and value['category'] == 'expression':
        changes['her/evolution/expressions.md'] = expression_changes(config, value)
    expression_path = config.root / 'her/evolution/expressions.md'
    if not private and value['category'] != 'expression' and expression_path.exists():
        cleaned = expression_changes(config)
        if cleaned != read_text(expression_path):
            changes['her/evolution/expressions.md'] = cleaned
    for rel in changes:
        config.authorize(root / rel)
    return root, changes


def consume(config, store, dry_run=False):
    proc = processor_config(config)
    output = proc.resolve(proc.data['output_dir'])
    counts = {'consumed': 0, 'duplicate': 0, 'invalid': 0, 'normal': 0, 'private': 0}
    # Deliberately nonrecursive: staging and nested files are never candidates.
    for path in sorted(output.glob('*.jsonl')):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > config.data['max_candidate_bytes']:
            counts['invalid'] += 1
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError):
            counts['invalid'] += 1
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if not CANDIDATES.is_valid(raw) or raw['id'] != candidate_id(raw):
                    raise ValueError()
                if raw['category'] == 'none' or any(s['trait'] not in config.personality['traits'] for s in raw['trait_signals']):
                    raise ValueError()
                if len({s['trait'] for s in raw['trait_signals']}) != len(raw['trait_signals']):
                    raise ValueError()
                # Reapply monotone privacy guard at the trust boundary.
                value = sensitive_guard(raw, {'user': '', 'assistant': ''}, proc.data['sensitivity'])
                if value['sensitivity'] == 'normal' and value['category'] == 'expression' and not expression_allowed(value, proc.data.get('expressions', {})):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                counts['invalid'] += 1
                continue
            fingerprint = digest(raw)
            old = store.db.execute('SELECT fingerprint FROM consumed WHERE id=?', (value['id'],)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise EngineError('candidate_id_conflict')
                counts['duplicate'] += 1
                continue
            root, changes = route(config, value)
            private = value['sensitivity'] != 'normal'
            if not dry_run:
                gitops.transaction(config, root, 'consume:' + value['id'], changes, 'xq-memory: ' + value['id'])
                with store.db:
                    store.db.execute('INSERT INTO consumed(id,fingerprint,sensitivity,payload,consumed_at) VALUES(?,?,?,?,?)',
                                     (value['id'], fingerprint, value['sensitivity'], None if private else canonical(value), now()))
            counts['consumed'] += 1
            counts['private' if private else 'normal'] += 1
    return counts


def evidence(store, ids):
    result = []
    for item in ids:
        row = store.db.execute("SELECT payload FROM consumed WHERE id=? AND sensitivity='normal'", (item,)).fetchone()
        if row is None or row['payload'] is None:
            raise EngineError('unknown_or_private_evidence')
        result.append(json.loads(row['payload']))
    return result


def guard(config, store, proposal, clock=None, owner_approved=False):
    """Reevaluated at apply time; pending cannot bypass evidence/step guards."""
    result = deepcopy(proposal)
    result['original_delta'] = proposal.get('original_delta', proposal['delta'])
    raw = {key: proposal[key] for key in ('trait', 'delta', 'evidence', 'counter_evidence', 'reason')}
    if not PROPOSALS.is_valid({'proposals': [raw]}):
        result['status'], result['codes'] = 'rejected', ['proposal_schema']
        return result
    if proposal.get('origin') == 'deterministic/v1' and (
            proposal['delta'] not in (-1, 1) or
            reflection.validate({'reviews': [proposal.get('review')]}, [proposal]) is not None or
            proposal['review']['decision'] != 'approve'):
        result['status'], result['codes'] = 'rejected', ['review_not_approved']
        return result
    maximum = config.threshold('max_step_per_trait')
    result['delta'] = max(-maximum, min(maximum, proposal['delta']))
    result['status'], result['codes'] = 'ready', []
    trait = config.personality['traits'].get(result['trait'])
    if trait is None:
        result['status'], result['codes'] = 'rejected', ['unknown_trait']
        return result
    try:
        rows = evidence(store, result['evidence'])
        evidence(store, result['counter_evidence'])
    except EngineError:
        result['status'], result['codes'] = 'rejected', ['unknown_or_private_evidence']
        return result
    if len(rows) < config.threshold('min_evidence_episodes'):
        result['codes'].append('insufficient_episodes')
    if len({(r['source']['kind'], r['source']['session']) for r in rows}) < config.threshold('min_evidence_sessions'):
        result['codes'].append('insufficient_sessions')
    if config.rules.get('forbid_sycophancy') is not True or config.rules.get('must_stay_in_range') is not True:
        raise EngineError('required_guard_disabled')
    if rows and all(r['praise_only'] for r in rows):
        result['codes'].append('praise_only')
    eligible = [r for r in rows if not r['praise_only']]
    if len(eligible) < config.threshold('min_evidence_episodes'):
        result['codes'].append('insufficient_nonpraise_episodes')
    if len({(r['source']['kind'], r['source']['session']) for r in eligible}) < config.threshold('min_evidence_sessions'):
        result['codes'].append('insufficient_nonpraise_sessions')
    if any(not any(s['trait'] == result['trait'] for s in r['trait_signals']) for r in rows):
        result['codes'].append('unsupported_trait_evidence')
    if result['codes']:
        result['status'] = 'rejected'
        return result
    result['before'] = trait['value']
    result['after'] = trait['value'] + result['delta']
    if not trait['range'][0] <= result['after'] <= trait['range'][1]:
        result['codes'].append('outside_range')
    clock = clock or datetime.now(timezone.utc)
    since = clock - timedelta(days=config.threshold('drift_window_days'))
    drift = 0
    # Include applied changes even if later reverted: gross drift must not reset
    # just because a direction was undone. Include reversal magnitude as well.
    for row in store.db.execute('SELECT document,applied_at,reverted_at FROM proposals WHERE applied_at IS NOT NULL'):
        document = json.loads(row['document'])
        if document['trait'] != result['trait']:
            continue
        if datetime.fromisoformat(row['applied_at']) >= since:
            drift += abs(document['delta'])
        if row['reverted_at'] and datetime.fromisoformat(row['reverted_at']) >= since:
            drift += abs(document['delta'])
    result['drift_before'] = drift
    if drift + abs(result['delta']) > config.threshold('monthly_drift_needs_approval'):
        result['codes'].append('monthly_drift')
    if result['codes']:
        if owner_approved:
            result['owner_overrides'] = list(result['codes'])
            result['codes'] = []
            result['owner_approved'] = True
        else:
            result['status'] = 'pending'
    return result


def store_proposal(config, store, value):
    previous = store.db.execute('SELECT status FROM proposals WHERE id=?', (value['id'],)).fetchone()
    path = config.root / 'her/evolution/proposals' / value['status'] / (safe_id(value['id']) + '.json')
    output = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    config.authorize(path)
    if path.exists() and read_text(path) != output:
        row = store.db.execute('SELECT document FROM proposals WHERE id=?', (value['id'],)).fetchone()
        if row is None or json.loads(read_text(path)) != json.loads(row['document']):
            raise EngineError('proposal_file_conflict')
        config.write(path, output)
    elif not path.exists():
        config.write(path, output)
    with store.db:
        store.db.execute('INSERT INTO proposals(id,document,status) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document,status=excluded.status',
                         (value['id'], canonical(value), value['status']))
    if value['status'] == 'pending' and (previous is None or previous['status'] != 'pending'):
        try:
            notify.pending(config, [value])
        except Exception:
            pass  # Desktop/session/notification failures never roll back proposals.


def resolve_pending(config, value, status):
    """Keep the audit file, update its state so loaders don't announce archives."""
    path = config.root / 'her/evolution/proposals/pending' / (safe_id(value['id']) + '.json')
    if path.exists():
        old = json.loads(read_text(path))
        if old['id'] != value['id']:
            raise EngineError('pending_file_conflict')
        if old.get('status') == status:
            return
        old['status'] = status
        if value.get('owner_approved'):
            old['owner_approved'] = True
            old['owner_overrides'] = value.get('owner_overrides', [])
        if 'owner_rejected' in value.get('codes', []):
            old['owner_rejected'] = True
        config.write(path, json.dumps(old, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def local_reflection(config, episodes, candidates):
    return reflection.review(config, episodes, candidates, request_reflection)


def request_reflection(endpoint, body, settings):
    request = Request(endpoint, canonical(body).encode('utf-8'), {'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=settings['timeout_seconds']) as response:
            raw = response.read(settings['max_response_bytes'] + 1)
        if len(raw) > settings['max_response_bytes']:
            raise EngineError('reflection_response_limit')
    except (HTTPError, URLError, OSError, HTTPException) as exc:
        if isinstance(exc, HTTPError):
            exc.close()
        raise EngineError('local_reflector_unavailable') from None
    try:
        choice = json.loads(raw)['choices'][0]
        if choice.get('finish_reason') in ('length', 'tool_calls', 'content_filter'):
            raise ValueError()
        text = choice['message']['content'].strip()
        if text.startswith('```json') and text.endswith('```'):
            text = text[7:-3].strip()
        value = json.loads(text)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise EngineError('invalid_reflection_response') from None
    return value


def reflect(config, store, dry_run=False):
    # A pending batch is frozen before the HTTP request. New episodes must not
    # replace its evidence when the reviewer is unavailable or its response fails.
    has_batches = store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_batches'").fetchone()
    waiting = store.db.execute("SELECT * FROM review_batches WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone() if has_batches else None
    rows = store.db.execute("SELECT payload FROM consumed WHERE sensitivity='normal' AND reflected=0 ORDER BY consumed_at,id LIMIT ?",
                            (config.data['max_reflection_episodes'],)).fetchall()
    if waiting is None and len(rows) < config.data['reflect_every']:
        return {'triggered': False, 'available': len(rows)}
    # Fail closed BEFORE sending data if lock thresholds are incomplete.
    for key in ('min_evidence_episodes', 'min_evidence_sessions', 'drift_window_days'):
        config.threshold(key)
    if dry_run:
        return {'triggered': True, 'would_reflect': len(rows), 'network_called': False}
    if waiting:
        saved = json.loads(waiting['document'])
        batch = waiting['id']
        episodes = evidence(store, saved['episodes'])
    else:
        episodes = [json.loads(row['payload']) for row in rows]
        batch = digest(['deterministic/v1', [r['id'] for r in episodes]])[:16]
        candidates, statistics = reflection.nominate(config, episodes, batch)
        saved = {'episodes': [r['id'] for r in episodes], 'candidates': candidates,
                 'statistics': statistics, 'created_at': now()}
        with store.db:
            store.db.execute('INSERT INTO review_batches VALUES(?,?,?)', (batch, canonical(saved), 'pending'))
    candidates = saved['candidates']
    expected, statistics = reflection.nominate(config, episodes, batch)
    if candidates != expected or saved['statistics'] != statistics:
        raise EngineError('review_batch_conflict')
    response = saved.get('response')
    if response is None:
        response = local_reflection(config, episodes, candidates) if candidates else {'reviews': []}
    if reflection.validate(response, candidates) is not None:
        raise EngineError('invalid_reflection_response')
    # Reclassify fresh AND cached output; unsafe text never enters public her/.
    proc = processor_config(config)
    content = canonical(response).casefold()
    if any(word.casefold() in content for words in proc.data['sensitivity']['keywords'].values() for word in words):
        raise EngineError('sensitive_reflection_rejected')
    saved['response'] = response
    with store.db:
        store.db.execute('UPDATE review_batches SET document=? WHERE id=?', (canonical(saved), batch))
    decisions = {r['id']: r for r in response['reviews']}
    counts = {'triggered': True, 'ready': 0, 'pending': 0, 'rejected': 0, 'applied': 0}
    for raw in candidates:
        decision = decisions[raw['id']]
        value = {**raw, 'batch': batch, 'created_at': saved['created_at'],
                 'origin': 'deterministic/v1', 'review': decision}
        existing = store.db.execute('SELECT status FROM proposals WHERE id=?', (value['id'],)).fetchone()
        if existing:
            continue
        if decision['decision'] == 'veto':
            value.update(status='rejected', codes=['model_veto'], original_delta=raw['delta'])
        else:
            value = guard(config, store, value)
        store_proposal(config, store, value)
        counts[value['status']] += 1
    with store.db:
        store.db.executemany('UPDATE consumed SET reflected=1 WHERE id=?', [(r['id'],) for r in episodes])
        store.db.execute('INSERT OR IGNORE INTO reflections VALUES(?,?)', (batch, now()))
        store.db.execute("UPDATE review_batches SET status='complete' WHERE id=?", (batch,))
    # Each ready proposal is reevaluated against the latest personality/drift.
    counts['applied'] = apply(config, store)['applied']
    return counts


def apply(config, store, proposal_id=None, dry_run=False, owner_approved=False):
    args = (safe_id(proposal_id),) if proposal_id else ()
    query = 'SELECT * FROM proposals WHERE id=?' if proposal_id else "SELECT * FROM proposals WHERE status='ready' ORDER BY id"
    rows = store.db.execute(query, args).fetchall()
    if proposal_id and not rows:
        raise EngineError('proposal_not_found')
    counts = {'applied': 0, 'pending': 0, 'rejected': 0, 'unchanged': 0}
    for row in rows:
        if row['status'] in ('applied', 'reverted', 'rejected'):
            if not dry_run:
                resolve_pending(config, json.loads(row['document']), row['status'])
            counts['unchanged'] += 1
            continue
        original = json.loads(row['document'])
        # A prior in-flight application must recover its exact bytes before
        # reading potentially already-updated personality values.
        journal = config.cache / 'transactions' / (digest('apply:' + row['id']) + '.json')
        if journal.exists() and not dry_run:
            record = json.loads(read_text(journal))
            changes = {rel: gitops.decode(data).decode('utf-8') for rel, data in record['after'].items()}
            value = original
            sha = gitops.transaction(config, config.root, 'apply:' + row['id'], changes,
                                     'xq-evolve: ' + row['id'] + ' ' + value['trait'] + ' ' + format(value['delta'], '+d'))
        else:
            config.personality = json.loads(read_text(config.personality_path))
            value = guard(config, store, original, owner_approved=owner_approved)
            if value['status'] != 'ready':
                counts[value['status']] += 1
                if not dry_run:
                    if value['status'] == 'rejected':
                        resolve_pending(config, value, 'rejected')
                    store_proposal(config, store, value)
                continue
            personality = deepcopy(config.personality)
            personality['traits'][value['trait']]['value'] = value['after']
            marker = '<!-- proposal:' + value['id'] + ' -->'
            log_path = config.root / 'her/evolution/log.md'
            config.authorize(log_path)
            log = read_text(log_path) or '# 人格演化记录\n'
            if marker in log:
                raise EngineError('proposal_already_in_log')
            log += '\n' + marker + '\n- ' + value['trait'] + ': ' + str(value['before']) + ' → ' + str(value['after'])
            log += ' (' + format(value['delta'], '+d') + '; original_delta=' + str(value['original_delta']) + ')\n'
            log += '- evidence: ' + ', '.join(value['evidence']) + '\n'
            if value.get('owner_approved'):
                log += '- owner_approved: true; overrides=' + ','.join(value.get('owner_overrides', [])) + '\n'
            changes = {'her/personality.json': json.dumps(personality, ensure_ascii=False, indent=2) + '\n',
                       'her/evolution/log.md': log}
            for rel in changes:
                config.authorize(config.root / rel)
            if dry_run:
                counts['applied'] += 1
                continue
            # The first evolution log is committed independently so git revert
            # of any proposal only modifies existing files, never deletes one.
            if not log_path.exists():
                gitops.transaction(config, config.root, 'initialize:evolution-log',
                                   {'her/evolution/log.md': '# 人格演化记录\n'}, 'xq-memory: initialize evolution log')
            # Save checked values before the transaction for exact crash recovery.
            with store.db:
                store.db.execute('UPDATE proposals SET document=? WHERE id=?', (canonical(value), value['id']))
            sha = gitops.transaction(config, config.root, 'apply:' + row['id'], changes,
                                     'xq-evolve: ' + row['id'] + ' ' + value['trait'] + ' ' + format(value['delta'], '+d'))
        resolve_pending(config, value, 'applied')
        with store.db:
            value['status'] = 'applied'
            store.db.execute("UPDATE proposals SET document=?,status='applied',commit_sha=?,applied_at=? WHERE id=?",
                             (canonical(value), sha, now(), row['id']))
        config.personality = json.loads(read_text(config.personality_path))
        counts['applied'] += 1
    return counts


def review(config, store, proposal_id, approve, owner_approved=False, dry_run=False):
    if not owner_approved:
        raise EngineError('owner_approval_flag_required')
    row = store.db.execute('SELECT * FROM proposals WHERE id=?', (safe_id(proposal_id),)).fetchone()
    if row is None:
        raise EngineError('proposal_not_found')
    if row['status'] in ('applied', 'rejected', 'reverted'):
        if not dry_run:
            resolve_pending(config, json.loads(row['document']), row['status'])
        return {'unchanged': 1}
    if row['status'] != 'pending':
        raise EngineError('proposal_not_pending')
    if approve:
        return apply(config, store, proposal_id, dry_run, owner_approved=True)
    if not dry_run:
        value = json.loads(row['document'])
        value.update(status='rejected', codes=['owner_rejected'])
        # Mark the existing pending audit file before the ledger; no deletion.
        resolve_pending(config, value, 'rejected')
        store_proposal(config, store, value)
    return {'rejected': 1}


def rollback(config, store, proposal_id, dry_run=False):
    row = store.db.execute('SELECT * FROM proposals WHERE id=?', (safe_id(proposal_id),)).fetchone()
    if row is None or row['status'] not in ('applied', 'reverted'):
        raise EngineError('proposal_not_applied')
    if row['status'] == 'reverted':
        return {'reverted': 0, 'unchanged': 1}
    if dry_run:
        for rel in ('her/personality.json', 'her/evolution/log.md'):
            config.authorize(config.root / rel)
        return {'would_revert': 1}
    gitops.revert(config, row['id'], row['commit_sha'])
    with store.db:
        store.db.execute("UPDATE proposals SET status='reverted',reverted_at=? WHERE id=?", (now(), row['id']))
    return {'reverted': 1}


def status(config, store):
    missing = []
    for rel in ('her/relationship.md', 'her/personality.json', 'her/evolution/log.md', 'her/episodes/2000-01/0000000000000000.md'):
        try:
            config.authorize(config.root / rel)
        except EngineError:
            missing.append(rel)
    return {'consumed': dict(store.db.execute('SELECT sensitivity,count(*) FROM consumed GROUP BY sensitivity').fetchall()),
            'proposals': dict(store.db.execute('SELECT status,count(*) FROM proposals GROUP BY status').fetchall()),
            'unreflected_normal': store.db.execute("SELECT count(*) FROM consumed WHERE sensitivity='normal' AND reflected=0").fetchone()[0],
            'traits': {key: item['value'] for key, item in config.personality['traits'].items()},
            'write_policy_missing': missing,
            'lock_missing': [key for key in ('min_evidence_episodes', 'min_evidence_sessions', 'drift_window_days') if key not in config.rules]}


def _run(config, command, proposal_id=None, dry_run=False, owner_approved=False):
    if command == 'sync':
        from .snapshots import sync
        return sync(config, dry_run)
    if command in ('approve', 'reject') and not owner_approved:
        raise EngineError('owner_approval_flag_required')
    store = Store(config, readonly=dry_run or command == 'status')
    try:
        if command in ('collect', 'extract'):
            processor = {'skipped': 'dry_run'} if dry_run else (
                pipeline.collect(processor_config(config)) if command == 'collect' else pipeline.extract_pending(processor_config(config)))
            result = {'processor': processor, 'candidates': consume(config, store, dry_run)}
            result['reflection'] = reflect(config, store, dry_run)
            return result
        if command == 'reflect':
            return reflect(config, store, dry_run)
        if command == 'apply':
            return apply(config, store, proposal_id, dry_run)
        if command == 'rollback':
            return rollback(config, store, proposal_id, dry_run)
        if command in ('approve', 'reject'):
            return review(config, store, proposal_id, command == 'approve', owner_approved, dry_run)
        if command == 'status':
            return status(config, store)
        raise EngineError('unknown_command')
    finally:
        store.close()


def run(config, command, proposal_id=None, dry_run=False, owner_approved=False):
    auto = (not dry_run and command not in ('sync', 'status')
            and config.data.get('sync', {}).get('automatic', False))
    result = None
    if auto:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from persona_loader import load_persona
        before = load_persona(config.root / 'her')
    try:
        result = _run(config, command, proposal_id, dry_run, owner_approved)
        return result
    finally:
        if auto and load_persona(config.root / 'her') != before:
            from .snapshots import sync
            try:
                synced = sync(config)
                if result is not None:
                    result['sync'] = synced
            except Exception:
                if result is not None:
                    raise EngineError('automatic_sync_failed') from None
