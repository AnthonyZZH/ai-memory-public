"""Single-direction main-vault backup. Standard library only; no model or vault writes."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import threading
import time
import uuid

SSH_ALIAS = "library-host"
REMOTE_ROOT = r"C:\AI-Library\main\vault"
BACKUP_ROOT = Path(r"E:\AI-Library-Backups")
SSH_EXE = r"C:\Windows\System32\OpenSSH\ssh.exe"
MAX_FILES = 100_000
MAX_BYTES = 1024 * 1024 * 1024
MAX_ATTEMPTS = 3
SSH_OPTIONS = ["-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o",
               "ConnectionAttempts=1", "-o", "StrictHostKeyChecking=yes", "-o",
               "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2"]
MANIFEST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
  $root = [IO.Path]::GetFullPath('C:\AI-Library\main\vault').TrimEnd('\')
  $item = Get-Item -LiteralPath $root -Force
  if (-not $item.PSIsContainer) { throw 'invalid root' }
  $ancestor = $item
  while ($null -ne $ancestor) {
    if (($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'reparse' }
    $ancestor = $ancestor.Parent
  }
  $pending = New-Object 'System.Collections.Generic.Stack[string]'
  $files = New-Object 'System.Collections.Generic.List[object]'
  $dirs = New-Object 'System.Collections.Generic.List[string]'
  $pending.Push($root)
  while ($pending.Count -gt 0) {
    $directory = $pending.Pop()
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force)) {
      if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'reparse' }
      if (-not $entry.FullName.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'outside' }
      $relative = $entry.FullName.Substring($root.Length + 1).Replace('\', '/')
      if ($entry.PSIsContainer) { $dirs.Add($relative); $pending.Push($entry.FullName); continue }
      $length = $entry.Length
      $written = $entry.LastWriteTimeUtc.Ticks
      $digest = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      $entry.Refresh()
      if (-not $entry.Exists -or $entry.Length -ne $length -or $entry.LastWriteTimeUtc.Ticks -ne $written -or
          ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'changed' }
      $files.Add([ordered]@{ path=$relative; size=$length; sha256=$digest })
    }
  }
  $manifest = [ordered]@{ version=1; root=$root; directories=@($dirs | Sort-Object); files=@($files | Sort-Object path) }
  $json = ConvertTo-Json -InputObject $manifest -Depth 8 -Compress
  [Console]::Out.WriteLine('XIAOQIAN_MANIFEST_V1:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
} catch { [Console]::Error.WriteLine('MAIN_MANIFEST_FAILED'); exit 21 }
"""


class BackupError(Exception):
    """Only fixed safe codes are printed or persisted."""


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise BackupError("MANIFEST_PATH_INVALID")
    if any(ord(c) < 32 for c in value) or any(c in value for c in "\\:") or value.startswith("/"):
        raise BackupError("MANIFEST_PATH_INVALID")
    parts = value.split("/")
    if any(not p or p in (".", "..") or p.rstrip(" .") != p for p in parts):
        raise BackupError("MANIFEST_PATH_INVALID")
    if any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts):
        raise BackupError("MANIFEST_PATH_INVALID")
    return value


def validate_manifest(value: object) -> dict:
    if not isinstance(value, dict) or value.get("version") != 1 or value.get("root") != REMOTE_ROOT:
        raise BackupError("MANIFEST_ROOT_INVALID")
    files, directories = value.get("files"), value.get("directories")
    if not isinstance(files, list) or not isinstance(directories, list) or not 0 < len(files) <= MAX_FILES:
        raise BackupError("MANIFEST_EMPTY_OR_INVALID")
    seen, clean_files, clean_dirs, size = set(), [], [], 0
    for entry in directories:
        path = relative_path(entry)
        if path.casefold() in seen:
            raise BackupError("MANIFEST_DUPLICATE_PATH")
        seen.add(path.casefold())
        clean_dirs.append(path)
    for entry in files:
        if not isinstance(entry, dict):
            raise BackupError("MANIFEST_FILE_INVALID")
        path = relative_path(entry.get("path"))
        length, sha = entry.get("size"), entry.get("sha256")
        if type(length) is not int or length < 0 or not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise BackupError("MANIFEST_FILE_INVALID")
        if path.casefold() in seen:
            raise BackupError("MANIFEST_DUPLICATE_PATH")
        seen.add(path.casefold())
        size += length
        clean_files.append({"path": path, "size": length, "sha256": sha})
    if size > MAX_BYTES:
        raise BackupError("MANIFEST_SIZE_LIMIT")
    known_dirs = set(clean_dirs)
    for path in clean_dirs + [f["path"] for f in clean_files]:
        components = path.split("/")
        if any("/".join(components[:i]) not in known_dirs for i in range(1, len(components))):
            raise BackupError("MANIFEST_PARENT_MISSING")
    return {"version": 1, "root": REMOTE_ROOT, "directories": sorted(clean_dirs),
            "files": sorted(clean_files, key=lambda x: x["path"])}


def no_reparse(path: Path) -> None:
    for ancestor in reversed([path, *path.parents]):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if ancestor.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise BackupError("LOCAL_REPARSE_DENIED")


def write_json_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def copy_bounded(source, output, limit: int) -> None:
    count = 0
    while chunk := source.read(1024 * 1024):
        count += len(chunk)
        if count > limit:
            raise BackupError("TRANSFER_SIZE_LIMIT")
        output.write(chunk)


class Remote:
    def command(self, command: str, *, destination: Path | None = None) -> bytes:
        args = [SSH_EXE, *SSH_OPTIONS, SSH_ALIAS, command]
        limit = MAX_BYTES + 128 * 1024 * 1024 if destination else 16 * 1024 * 1024
        expired = threading.Event()
        try:
            with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
                def timeout():
                    expired.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
                timer = threading.Timer(180, timeout)
                timer.daemon = True
                timer.start()
                try:
                    if destination:
                        with destination.open("xb") as output:
                            copy_bounded(process.stdout, output, limit)
                        payload = b""
                    else:
                        output = io.BytesIO()
                        copy_bounded(process.stdout, output, limit)
                        payload = output.getvalue()
                    status = process.wait()
                finally:
                    timer.cancel()
                    if process.poll() is None:
                        process.kill()
                        process.wait()
        except OSError:
            raise BackupError("SSH_UNAVAILABLE") from None
        if expired.is_set():
            raise BackupError("SSH_TIMEOUT")
        if status != 0:
            raise BackupError("SSH_COMMAND_FAILED")
        return payload

    def manifest(self) -> dict:
        import base64
        encoded = base64.b64encode(MANIFEST_SCRIPT.encode("utf-16-le")).decode("ascii")
        result = self.command(f"powershell.exe -NoProfile -NonInteractive -EncodedCommand {encoded}")
        if len(result) > 16 * 1024 * 1024:
            raise BackupError("MANIFEST_SIZE_LIMIT")
        rows = [line[len(b"XIAOQIAN_MANIFEST_V1:"):] for line in result.splitlines()
                if line.startswith(b"XIAOQIAN_MANIFEST_V1:")]
        if len(rows) != 1:
            raise BackupError("MANIFEST_PROTOCOL_INVALID")
        try:
            value = json.loads(base64.b64decode(rows[0], validate=True).decode("utf-8"))
        except (ValueError, UnicodeError):
            raise BackupError("MANIFEST_PROTOCOL_INVALID") from None
        return validate_manifest(value)

    def archive(self, destination: Path) -> None:
        # No -h/-L: tar preserves links as links; extraction below rejects all links.
        self.command(r"C:\Windows\System32\tar.exe -cf - -C C:\AI-Library\main\vault .", destination=destination)
        if destination.stat().st_size > MAX_BYTES + 128 * 1024 * 1024:
            raise BackupError("ARCHIVE_SIZE_LIMIT")


def extract_verified(archive: Path, destination: Path, manifest: dict) -> None:
    expected = {item["path"]: item for item in manifest["files"]}
    expected_dirs, seen, seen_dirs = set(manifest["directories"]), set(), set()
    destination.mkdir()
    try:
        with tarfile.open(archive, mode="r:") as bundle:
            for member in bundle:
                name = member.name
                if name in (".", "./") and member.isdir():
                    continue
                if name.startswith("./"):
                    name = name[2:]
                if member.isdir():
                    name = name.rstrip("/")
                name = relative_path(name)
                target = destination.joinpath(*name.split("/"))
                if member.isdir() and name in expected_dirs and name not in seen_dirs:
                    target.mkdir(parents=True, exist_ok=True)
                    seen_dirs.add(name)
                    continue
                if not member.isfile() or name not in expected or name in seen:
                    raise BackupError("ARCHIVE_ENTRY_DENIED")
                entry = expected[name]
                if member.size != entry["size"]:
                    raise BackupError("ARCHIVE_MANIFEST_MISMATCH")
                target.parent.mkdir(parents=True, exist_ok=True)
                no_reparse(target)
                digest, count = hashlib.sha256(), 0
                source = bundle.extractfile(member)
                if source is None:
                    raise BackupError("ARCHIVE_ENTRY_DENIED")
                with source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        count += len(chunk)
                        if count > entry["size"]:
                            raise BackupError("ARCHIVE_MANIFEST_MISMATCH")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if count != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise BackupError("LOCAL_HASH_MISMATCH")
                seen.add(name)
    except (tarfile.TarError, EOFError):
        raise BackupError("ARCHIVE_INVALID") from None
    if seen != set(expected) or seen_dirs != expected_dirs:
        raise BackupError("ARCHIVE_MANIFEST_MISMATCH")


def verify_tree(destination: Path, manifest: dict) -> None:
    expected = {entry["path"]: entry for entry in manifest["files"]}
    found_files, found_dirs = set(), set()
    for current, dirs, files in os.walk(destination, followlinks=False):
        for name in dirs + files:
            path = Path(current) / name
            no_reparse(path)
            relative = path.relative_to(destination).as_posix()
            if path.is_dir():
                found_dirs.add(relative)
                continue
            if relative not in expected:
                raise BackupError("LOCAL_TREE_MISMATCH")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if path.stat().st_size != expected[relative]["size"] or digest.hexdigest() != expected[relative]["sha256"]:
                raise BackupError("LOCAL_HASH_MISMATCH")
            found_files.add(relative)
    if found_files != set(expected) or found_dirs != set(manifest["directories"]):
        raise BackupError("LOCAL_TREE_MISMATCH")


def last_success_day(root: Path) -> dt.date | None:
    days = []
    for marker in root.glob("*/attempt-*/SUCCESS.json"):
        try:
            no_reparse(marker)
            value = json.loads(marker.read_text(encoding="utf-8"))
            if value.get("status") == "verified":
                days.append(dt.date.fromisoformat(value["due_day"]))
        except (OSError, ValueError, KeyError, BackupError):
            continue
    return max(days, default=None)


@contextlib.contextmanager
def lock(root: Path):
    import msvcrt
    lock_path = root / ".backup.lock"
    no_reparse(lock_path)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BackupError("BACKUP_ALREADY_RUNNING") from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def backup(root: Path, remote: Remote, due_day: dt.date, *, retries: int = MAX_ATTEMPTS, sleeper=time.sleep) -> dict:
    no_reparse(root)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = root / run_id
    run_dir.mkdir()
    last_code = "BACKUP_FAILED"
    for number in range(1, retries + 1):
        attempt = run_dir / f"attempt-{number}"
        attempt.mkdir()
        try:
            before = validate_manifest(remote.manifest())
            write_json_new(attempt / "MANIFEST.before.json", before)
            remote.archive(attempt / "bundle.tar")
            after = validate_manifest(remote.manifest())
            write_json_new(attempt / "MANIFEST.after.json", after)
            if before != after:
                raise BackupError("REMOTE_CHANGED_DURING_COPY")
            extract_verified(attempt / "bundle.tar", attempt / "vault", before)
            verify_tree(attempt / "vault", before)
            summary = {"status": "verified", "finished_utc": now_utc(), "due_day": due_day.isoformat(),
                       "files": len(before["files"]), "bytes": sum(x["size"] for x in before["files"]),
                       "consistency": "matching-before-after-and-local-sha256-not-atomic"}
            write_json_new(attempt / "MANIFEST.json", before)
            write_json_new(attempt / "SUCCESS.json", summary)
            return {**summary, "snapshot": str(attempt)}
        except (BackupError, OSError) as error:
            last_code = str(error) if isinstance(error, BackupError) else "LOCAL_IO_FAILED"
            write_json_new(attempt / "FAILED.json", {"status": "failed", "code": last_code, "finished_utc": now_utc()})
            if number < retries:
                sleeper(2)
    raise BackupError(last_code)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--due-day", required=True, help="Melbourne date for the most recent scheduled 20:00 slot")
    parser.add_argument("--force", action="store_true", help="Explicit manual verification run only")
    args = parser.parse_args(argv)
    try:
        due = dt.date.fromisoformat(args.due_day)
        no_reparse(BACKUP_ROOT)
        BACKUP_ROOT.mkdir(exist_ok=True)
        no_reparse(BACKUP_ROOT)
        with lock(BACKUP_ROOT):
            previous = last_success_day(BACKUP_ROOT)
            if previous and previous >= due and not args.force:
                print(json.dumps({"status": "already_backed_up", "due_day": due.isoformat()}))
                return 0
            result = backup(BACKUP_ROOT, Remote(), due)
            print(json.dumps(result, ensure_ascii=True))
            return 0
    except (BackupError, OSError, ValueError) as error:
        code = str(error) if isinstance(error, BackupError) else "LOCAL_SETUP_FAILED"
        print(json.dumps({"status": "pending_next_run", "code": code, "time_utc": now_utc()}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
