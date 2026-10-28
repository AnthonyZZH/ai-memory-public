"""Local library checks; emit only a verdict table, never filenames or errors."""

import datetime as dt
import http.client
import json
import pathlib
import subprocess
import sys
import time

MAIN = pathlib.Path(r'E:\AI-Memory')
PRIVATE = pathlib.Path(r'E:\AI-Memory-private')
DAY = 86400
# Daily backups may run late via StartWhenAvailable after a late boot.
BACKUP_MAX_AGE = 36 * 3600


def handshake(port):
    """Send initialize and notifications/initialized, without tool requests."""
    headers = {'Content-Type': 'application/json',
               'Accept': 'application/json, text/event-stream'}
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
    try:
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2024-11-05', 'capabilities': {},
            'clientInfo': {'name': 'library-healthcheck', 'version': '1.0'}}}
        connection.request('POST', '/mcp', json.dumps(body), headers)
        response = connection.getresponse()
        if response.status != 200:
            return False
        session = response.getheader('Mcp-Session-Id')
        if 'text/event-stream' in response.getheader('Content-Type', ''):
            data = []
            size = 0
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                line = response.readline(65537)
                size += len(line)
                if not line or size > 1048576:
                    return False
                if line in (b'\n', b'\r\n') and data:
                    message = json.loads(b'\n'.join(data))
                    if message.get('id') == 1:
                        break
                    data = []
                elif line.startswith(b'data:'):
                    data.append(line[5:].strip())
            else:
                return False
        else:
            raw = response.read(1048577)
            if len(raw) > 1048576:
                return False
            message = json.loads(raw)
        result = message.get('result', {})
        if (message.get('jsonrpc') != '2.0' or message.get('id') != 1
                or 'error' in message or not result.get('protocolVersion')
                or not isinstance(result.get('capabilities'), dict)
                or not isinstance(result.get('serverInfo'), dict)):
            return False
        connection.close()
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
        if session:
            headers['Mcp-Session-Id'] = session
        headers['MCP-Protocol-Version'] = result['protocolVersion']
        connection.request('POST', '/mcp', json.dumps({
            'jsonrpc': '2.0', 'method': 'notifications/initialized'}), headers)
        return connection.getresponse().status in (200, 202, 204)
    finally:
        connection.close()


def backup(root, now):
    """Use the newest completed, nonempty ZIP's local modification time."""
    candidates = [p for p in (root / 'backups').glob('AI-Memory-*.zip')
                  if p.is_file() and p.stat().st_size > 0]
    if not candidates:
        return False, 'MISSING'
    newest = max(p.stat().st_mtime for p in candidates)
    date = dt.datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M')
    return 0 <= now - newest <= BACKUP_MAX_AGE, date


def worktree(root, now):
    """Age is the oldest mtime among changed and untracked, nonignored files."""
    result = subprocess.run([
        'git', '--no-optional-locks', '-c', f'safe.directory={root.as_posix()}',
        '-C', str(root), 'status', '--porcelain=v1', '-z', '--untracked-files=all'],
        capture_output=True, timeout=10)
    if result.returncode:
        return False, 'GIT_ERROR'
    records = iter(result.stdout.split(b'\0'))
    modified = []
    for record in records:
        if not record:
            continue
        status = record[:2]
        modified.append(root / record[3:].decode('utf-8'))
        if b'R' in status or b'C' in status:
            next(records)  # porcelain -z includes the original path separately.
    if not modified:
        return True, 'CLEAN'
    times = []
    for path in modified:
        try:
            times.append(path.lstat().st_mtime)
        except FileNotFoundError:
            # Deleted files have no worktree mtime; cannot claim a fresh change.
            return False, f'files={len(modified)} AGE_UNKNOWN'
    age = max(0, now - min(times))
    return age <= DAY, f'files={len(modified)} oldest_hours={age / 3600:.1f}'


def guarded(operation):
    try:
        return operation()
    except Exception:
        return False, 'CHECK_ERROR'


def main():
    now = time.time()
    rows = []
    for label, port in [('main', 8767), ('private', 8768)]:
        rows.append((f'{label} MCP {port}', *guarded(
            lambda port=port: (handshake(port), 'initialize + initialized'))))
    for label, root in [('main', MAIN), ('private', PRIVATE)]:
        rows.append((f'{label} backup', *guarded(lambda root=root: backup(root, now))))
        rows.append((f'{label} worktree', *guarded(lambda root=root: worktree(root, now))))
    print('| Check | Result | Detail |')
    print('|---|---|---|')
    for name, ok, detail in rows:
        print(f'| {name} | {"PASS" if ok else "FAIL"} | {detail} |')
    return 0 if all(row[1] for row in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
