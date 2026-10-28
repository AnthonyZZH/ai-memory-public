"""Materialize pinned, content-verified vendor sources; never install or run them.

The default online path uses GitHub commit metadata + codeload. --source-root
uses read-only git archive on previously audited clones for offline tests.
Existing destinations and partial failures are preserved, never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 32 * 1024 * 1024


def digest_tree(root: Path) -> str:
    entries = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('source_symlink_rejected')
        if path.is_file():
            entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'xq-social-vendor/1'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('archive_size_limit')
    return data


def extract(data: bytes, target: Path, prefix: str = '') -> None:
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        members = archive.getmembers()
        if len(members) > 3000:
            raise ValueError('archive_member_limit')
        for member in members:
            name = member.name
            if prefix:
                if name.rstrip('/') == prefix.rstrip('/'):
                    continue
                if not name.startswith(prefix):
                    raise ValueError('archive_commit_prefix_mismatch')
                name = name[len(prefix):]
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                raise ValueError('archive_path_rejected')
            if not name or member.isdir():
                continue
            if not member.isfile() or member.size > 8 * 1024 * 1024:
                raise ValueError('archive_type_or_size_rejected')
            total += member.size
            if total > LIMIT:
                raise ValueError('archive_size_limit')
            path = target.joinpath(*relative.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as stream:
                with path.open('xb') as out:
                    out.write(stream.read())
            path.chmod(member.mode & 0o777)


def materialize(out: Path, source_root: Path | None = None, lock_path: Path | None = None) -> None:
    lock_path = lock_path or ROOT / 'vendor.lock'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    if lock.get('version') != 1:
        raise ValueError('lock_version_invalid')
    # Validate every patch before creating output or using the network.
    for item in lock['projects']:
        if not __import__('re').fullmatch(r'[a-z0-9-]+', item['name']):
            raise ValueError('project_name_invalid')
        if not __import__('re').fullmatch(r'[0-9a-f]{40}', item['commit']):
            raise ValueError('commit_invalid')
        for patch in item['patches']:
            path = (ROOT / patch['path']).resolve()
            if not path.is_relative_to(ROOT / 'patches'):
                raise ValueError('patch_path_rejected')
            if hashlib.sha256(path.read_bytes()).hexdigest() != patch['sha256']:
                raise ValueError('patch_digest_mismatch')
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS='1', GIT_CONFIG_NOSYSTEM='1')
    for item in lock['projects']:
        target = out / item['name']
        target.mkdir()
        sha = item['commit']
        if source_root is not None:
            repo = source_root / item['name']
            actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', sha + '^{commit}'], env=env, text=True).strip()
            if actual != sha:
                raise ValueError('commit_mismatch')
            data = subprocess.check_output(['git', '-c', 'core.autocrlf=false', '-C', str(repo), 'archive', '--format=tar', sha], env=env)
            if len(data) > LIMIT:
                raise ValueError('archive_size_limit')
            extract(data, target)
        else:
            repo = item['repository']
            if not __import__('re').fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repo):
                raise ValueError('repository_invalid')
            meta = json.loads(download(f'https://api.github.com/repos/{repo}/git/commits/{sha}'))
            if meta.get('sha') != sha:
                raise ValueError('commit_mismatch')
            data = download(f'https://codeload.github.com/{repo}/tar.gz/{sha}')
            extract(data, target, repo.split('/')[1] + '-' + sha + '/')
        if digest_tree(target) != item['tree_sha256']:
            raise ValueError('source_tree_digest_mismatch')
        for patch in item['patches']:
            path = ROOT / patch['path']
            command = ['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error-all']
            subprocess.run([*command, '--check', str(path)], cwd=target, env=env, check=True, capture_output=True)
            subprocess.run([*command, str(path)], cwd=target, env=env, check=True, capture_output=True)
        if digest_tree(target) != item['patched_tree_sha256']:
            raise ValueError('patched_tree_digest_mismatch')
        print(item['name'] + ': pinned_commit_verified patches_applied')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new destination; existing paths are rejected')
    parser.add_argument('--source-root', type=Path, help='offline audited git clones, no git writes')
    args = parser.parse_args()
    try:
        materialize(args.out.resolve(), args.source_root)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError):
        print('vendor_build_failed; output_preserved; no_install_or_execution')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
