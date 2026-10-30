import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import backup_main as backup

# The managed Windows sandbox's default temp redirects to an unwritable location.
# Keep synthetic temporary trees under this known, non-reparse workspace directory.
TEST_ROOT = Path(__file__).resolve().parent / ".test-tmp"
TEST_ROOT.mkdir(exist_ok=True)
backup.no_reparse(TEST_ROOT)
tempfile.tempdir = str(TEST_ROOT)

DAY = dt.date(2026, 10, 29)
DATA = b"Synthetic backup fixture. No real notes.\n"


def manifest(data=DATA):
    return {"version": 1, "root": backup.REMOTE_ROOT, "directories": ["notes"], "files": [
        {"path": "notes/sample.md", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}]}


def archive(path, data=DATA, *, extra=None):
    with tarfile.open(path, "w") as bundle:
        directory = tarfile.TarInfo("./notes")
        directory.type = tarfile.DIRTYPE
        bundle.addfile(directory)
        info = tarfile.TarInfo("./notes/sample.md")
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))
        if extra:
            bundle.addfile(extra)


class FakeRemote:
    def __init__(self, versions=None, data=DATA, fail=False):
        self.versions = list(versions or [manifest(), manifest()])
        self.data, self.fail, self.calls = data, fail, 0

    def manifest(self):
        self.calls += 1
        if self.fail:
            raise backup.BackupError("SSH_COMMAND_FAILED")
        return self.versions.pop(0)

    def archive(self, destination):
        archive(destination, self.data)


class BackupTests(unittest.TestCase):
    def test_transfer_limit_is_enforced_before_excess_bytes_reach_disk(self):
        output = io.BytesIO()
        with self.assertRaisesRegex(backup.BackupError, "TRANSFER_SIZE_LIMIT"):
            backup.copy_bounded(io.BytesIO(b"x" * 2048), output, 1024)
        self.assertLessEqual(len(output.getvalue()), 1024)

    def test_manifest_refuses_empty_foreign_root_traversal_and_case_collisions(self):
        for bad_path in ["../x", "/x", "C:/x", "x\\y", "notes/../x", "notes/x.", "NUL", "notes//x"]:
            value = manifest()
            value["files"][0]["path"] = bad_path
            with self.subTest(path=bad_path), self.assertRaises(backup.BackupError):
                backup.validate_manifest(value)
        for value in [dict(manifest(), root="private"), dict(manifest(), files=[])]:
            with self.assertRaises(backup.BackupError):
                backup.validate_manifest(value)
        value = manifest()
        value["files"].append(dict(value["files"][0], path="NOTES/SAMPLE.MD"))
        with self.assertRaisesRegex(backup.BackupError, "DUPLICATE"):
            backup.validate_manifest(value)

    def test_verified_snapshot_and_second_run_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = backup.backup(root, FakeRemote(), DAY)
            second = backup.backup(root, FakeRemote(), DAY)
            self.assertNotEqual(first["snapshot"], second["snapshot"])
            self.assertEqual((Path(first["snapshot"]) / "vault/notes/sample.md").read_bytes(), DATA)
            self.assertEqual(first["files"], 1)
            self.assertEqual(backup.last_success_day(root), DAY)

    def test_changing_source_retries_bounded_and_keeps_failed_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            remote = FakeRemote([manifest(), manifest(b"changed"), manifest(), manifest()])
            result = backup.backup(Path(directory), remote, DAY, sleeper=lambda _: None)
            chosen = Path(result["snapshot"])
            self.assertEqual(chosen.name, "attempt-2")
            self.assertTrue((chosen.parent / "attempt-1/FAILED.json").is_file())
            self.assertTrue((chosen.parent / "attempt-1/bundle.tar").is_file())
            self.assertEqual(remote.calls, 4)

    def test_offline_run_leaves_failure_markers_without_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root, remote = Path(directory), FakeRemote(fail=True)
            with self.assertRaisesRegex(backup.BackupError, "SSH_COMMAND_FAILED"):
                backup.backup(root, remote, DAY, retries=3, sleeper=lambda _: None)
            self.assertEqual(remote.calls, 3)
            self.assertEqual(len(list(root.glob("*/attempt-*/FAILED.json"))), 3)
            self.assertIsNone(backup.last_success_day(root))

    def test_links_special_files_and_foreign_entries_never_extract(self):
        variants = [("notes/link", tarfile.SYMTYPE, "../../outside"),
                    ("notes/link", tarfile.LNKTYPE, "../../outside"),
                    ("../outside", tarfile.REGTYPE, ""),
                    ("notes/device", tarfile.CHRTYPE, ""),
                    ("foreign.md", tarfile.REGTYPE, "")]
        for name, kind, target in variants:
            with self.subTest(name=name, type=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                info = tarfile.TarInfo(name)
                info.type, info.linkname = kind, target
                archive(root / "bundle.tar", extra=info)
                with self.assertRaises(backup.BackupError):
                    backup.extract_verified(root / "bundle.tar", root / "vault", manifest())
                self.assertFalse((root / "outside").exists())

    def test_stable_remote_manifests_do_not_hide_corrupt_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(backup.BackupError):
                backup.backup(Path(directory), FakeRemote(data=b"different"), DAY, retries=1)
            self.assertFalse(list(Path(directory).glob("*/attempt-*/SUCCESS.json")))

    def test_local_tree_check_detects_post_extraction_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive(root / "bundle.tar")
            backup.extract_verified(root / "bundle.tar", root / "vault", manifest())
            (root / "vault/notes/sample.md").write_bytes(b"corrupt")
            with self.assertRaisesRegex(backup.BackupError, "LOCAL_HASH_MISMATCH"):
                backup.verify_tree(root / "vault", manifest())

    def test_remote_configuration_cannot_target_private_or_prompt_for_auth(self):
        self.assertEqual(backup.SSH_ALIAS, "library-host")
        self.assertEqual(backup.REMOTE_ROOT, r"C:\AI-Library\main\vault")
        self.assertIn("BatchMode=yes", backup.SSH_OPTIONS)
        self.assertIn("StrictHostKeyChecking=yes", backup.SSH_OPTIONS)
        self.assertNotIn("private", backup.MANIFEST_SCRIPT.lower())


if __name__ == "__main__":
    unittest.main()
