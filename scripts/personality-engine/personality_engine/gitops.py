"""Runtime-only git operations, exact path staging and retained recovery journal."""
import base64
import json
import os
from pathlib import Path
import subprocess

from .policy import EngineError, canonical, digest


def git(config, root, *args, check=True):
    # Do not inherit caller GIT_DIR/index overrides or permit repo hooks to send data.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    identity = config.data['git_identity']
    cache = config.private_cache if root == config.private else config.cache
    command = ['git', '-c', 'core.hooksPath=' + str(cache / 'disabled-hooks'),
               '-c', 'commit.gpgsign=false', '-c', 'core.quotePath=false',
               '-c', 'user.name=' + identity['name'], '-c', 'user.email=' + identity['email'],
               '-C', str(root), *args]
    result = subprocess.run(command, capture_output=True, env=env, timeout=60)
    if check and result.returncode:
        raise EngineError('git_operation_failed')
    return result


def head(config, root):
    return git(config, root, 'rev-parse', 'HEAD').stdout.decode('ascii').strip()


def check_repo(config, root):
    top = Path(git(config, root, 'rev-parse', '--show-toplevel').stdout.decode('utf-8').strip()).resolve()
    if top != root:
        raise EngineError('repository_root_mismatch')
    if git(config, root, 'diff', '--cached', '--name-only', '-z').stdout:
        raise EngineError('unrelated_staged_changes')
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD'):
        path = git(config, root, 'rev-parse', '--git-path', marker).stdout.decode('utf-8').strip()
        if (root / path).exists():
            raise EngineError('git_operation_in_progress')
    head(config, root)


def read_bytes(path):
    return path.read_bytes() if path.exists() else None


def encode(value):
    return None if value is None else base64.b64encode(value).decode('ascii')


def decode(value):
    return None if value is None else base64.b64decode(value)


def transaction(config, root, operation, changes, message):
    """Recover across write/commit/ledger interruptions without clobbering edits.

    Journals in each repository's cache retain before/after bytes. Private bytes
    stay in the private repository. No git reset/clean or automatic file deletion.
    """
    private = root == config.private
    cache = config.private_cache if private else config.cache
    journal = cache / 'transactions' / (digest(operation) + '.json')
    for rel in changes:
        authorized_root, actual = config.authorize(root / rel)
        if authorized_root != root or actual != rel:
            raise EngineError('transaction_path_mismatch')
    if journal.exists():
        record = json.loads(journal.read_text(encoding='utf-8'))
        if record['operation'] != operation or set(record['after']) != set(changes):
            raise EngineError('journal_conflict')
        for rel, content in changes.items():
            if decode(record['after'][rel]) != content.encode('utf-8'):
                raise EngineError('journal_payload_conflict')
    else:
        check_repo(config, root)
        if git(config, root, 'diff', '--name-only', '-z', '--', *changes).stdout:
            raise EngineError('target_has_uncommitted_changes')
        for rel in changes:
            if (root / rel).exists() and git(config, root, 'ls-files', '--error-unmatch', '--', rel, check=False).returncode:
                raise EngineError('target_has_untracked_content')
        record = {'operation': operation, 'before_head': head(config, root), 'commit': None,
                  'before': {rel: encode(read_bytes(root / rel)) for rel in changes},
                  'after': {rel: encode(value.encode('utf-8')) for rel, value in changes.items()}}
        config.operational(journal, canonical(record), private)
    trailer = 'Engine-Operation: ' + digest(operation)
    current_head = head(config, root)
    if record['commit']:
        if git(config, root, 'merge-base', '--is-ancestor', record['commit'], current_head, check=False).returncode:
            raise EngineError('recorded_commit_missing')
        return record['commit']
    # Only a matching most-recent commit can resolve a crash after commit.
    latest = git(config, root, 'log', '-1', '--format=%B').stdout.decode('utf-8')
    if trailer in latest.splitlines() and current_head != record['before_head']:
        record['commit'] = current_head
        config.operational(journal, canonical(record), private)
        return current_head
    if current_head != record['before_head']:
        raise EngineError('repository_changed_during_transaction')
    staged = set(filter(None, git(config, root, 'diff', '--cached', '--name-only', '-z').stdout.decode('utf-8').split('\0')))
    if not staged.issubset(changes):
        raise EngineError('unrelated_staged_changes')
    for rel in changes:
        path = root / rel
        current = read_bytes(path)
        if current not in (decode(record['before'][rel]), decode(record['after'][rel])):
            raise EngineError('concurrent_file_edit')
    for rel, value in changes.items():
        config.write(root / rel, value)
    git(config, root, 'add', '--', *changes)
    if head(config, root) != record['before_head']:
        raise EngineError('repository_changed_during_transaction')
    if not git(config, root, 'diff', '--cached', '--name-only', '-z').stdout:
        raise EngineError('empty_transaction')
    git(config, root, 'commit', '-m', message + '\n\n' + trailer)
    record['commit'] = head(config, root)
    config.operational(journal, canonical(record), private)
    return record['commit']


def revert(config, proposal_id, commit):
    root = config.root
    check_repo(config, root)
    expected = {'her/personality.json', 'her/evolution/log.md'}
    files = set(filter(None, git(config, root, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', commit).stdout.decode('utf-8').split('\0')))
    if files != expected:
        raise EngineError('rollback_commit_paths_mismatch')
    statuses = git(config, root, 'diff-tree', '--no-commit-id', '--name-status', '-r', commit).stdout.decode('utf-8').splitlines()
    if any(not line.startswith('M\t') for line in statuses):
        raise EngineError('rollback_would_create_or_delete_files')
    for rel in files:
        config.authorize(root / rel)
    if git(config, root, 'diff', '--name-only', '-z', '--', *files).stdout:
        raise EngineError('target_has_uncommitted_changes')
    # A retained intent supports recovery if the process stops after git revert.
    journal = config.cache / 'rollbacks' / (proposal_id + '.json')
    record = json.loads(journal.read_text(encoding='utf-8')) if journal.exists() else {'head': head(config, root), 'commit': commit}
    if record['commit'] != commit:
        raise EngineError('rollback_journal_conflict')
    current = head(config, root)
    if current != record['head']:
        message = git(config, root, 'log', '-1', '--format=%B').stdout.decode('utf-8')
        if 'This reverts commit ' + commit + '.' in message:
            return current
        raise EngineError('repository_changed_during_rollback')
    config.operational(journal, canonical(record))
    git(config, root, 'revert', '--no-edit', commit)
    return head(config, root)
