from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import mnemosyne


class TransactionJournalUnitTests(unittest.TestCase):
    """Verifies atomic transaction journal persistence, parsing, and summarization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mnemo_test_journal_")
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_journal_path_resolution(self):
        video = self.base / "clip.mp4"
        backup = self.base / "clip.mp4.bak"
        expected = self.base / f"clip.mp4{mnemosyne.TRANSACTION_JOURNAL_SUFFIX}"

        self.assertEqual(mnemosyne.get_transaction_journal_path(video), expected)
        self.assertEqual(mnemosyne.get_transaction_journal_path(backup), expected)

    def test_write_and_load_transaction_journal(self):
        video = self.base / "video.mkv"
        video.touch()

        # Write initial journal stage
        j_path = mnemosyne.write_transaction_journal(
            video,
            stage="transcoded",
            target_codec="libx264",
            verification={"metadata_ok": True, "decode_ok": True, "frame_check": "counted"},
        )
        self.assertIsNotNone(j_path)
        self.assertTrue(j_path.exists())

        loaded = mnemosyne.load_transaction_journal(video)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["stage"], "transcoded")
        self.assertEqual(loaded["target_codec"], "libx264")
        self.assertTrue(loaded["verification"]["metadata_ok"])

        # Update journal with next stage
        mnemosyne.write_transaction_journal(video, stage="verified_complete")
        reloaded = mnemosyne.load_transaction_journal(video)
        self.assertEqual(reloaded["stage"], "verified_complete")
        self.assertEqual(reloaded["target_codec"], "libx264")  # Preserved previous updates

        # Clear journal
        mnemosyne.clear_transaction_journal(video)
        self.assertIsNone(mnemosyne.load_transaction_journal(video))
        self.assertFalse(j_path.exists())

    def test_corrupted_journal_handling(self):
        video = self.base / "corrupt_video.mp4"
        video.touch()
        j_path = mnemosyne.get_transaction_journal_path(video)
        j_path.write_text("INVALID_JSON{broken", encoding="utf-8")

        # Loading corrupted json must not raise JSONDecodeError but return fail-safe dict
        with self.assertLogs(logger="", level="WARNING") as logs:
            journal = mnemosyne.load_transaction_journal(video)
        self.assertEqual(journal.get("stage"), "journal_unreadable")
        self.assertIn("Could not read transaction journal", "\n".join(logs.output))

    def test_summarize_transaction_journal_matrix(self):
        cases = [
            (None, ""),
            ({}, ""),
            ({"stage": "transcoding"}, "stage=transcoding"),
            (
                {"stage": "verified", "verification": {"metadata_ok": True, "decode_ok": True, "frame_check": "counted"}},
                "stage=verified | metadata=ok, decode=ok, frames=counted",
            ),
            (
                {"stage": "swap_failed", "last_error": "Permission Denied", "verification": {"metadata_ok": False}},
                "stage=swap_failed | metadata=fail | error=Permission Denied",
            ),
        ]
        for journal, expected in cases:
            self.assertEqual(mnemosyne.summarize_transaction_journal(journal), expected)


class CrashRecoveryAndRollbackTests(unittest.TestCase):
    """Verifies crash recovery, backup restoration modes, and rollback guarantees."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mnemo_test_recovery_")
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_restore_backup_mode_restore_success(self):
        bak = self.base / "original.mp4.bak"
        target = self.base / "original.mp4"
        bak.write_text("original_data", encoding="utf-8")

        success, preserved = mnemosyne.restore_backup_with_mode(bak, mode="restore")
        self.assertTrue(success)
        self.assertIsNone(preserved)
        self.assertTrue(target.exists())
        self.assertFalse(bak.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "original_data")

    def test_restore_backup_mode_restore_conflict_refusal(self):
        bak = self.base / "conflict.mp4.bak"
        current = self.base / "conflict.mp4"
        bak.write_text("backup_data", encoding="utf-8")
        current.write_text("current_data", encoding="utf-8")

        success, preserved = mnemosyne.restore_backup_with_mode(bak, mode="restore")
        self.assertFalse(success)
        self.assertIsNone(preserved)
        self.assertTrue(bak.exists())
        self.assertTrue(current.exists())
        self.assertEqual(current.read_text(encoding="utf-8"), "current_data")

    def test_restore_backup_mode_restore_and_preserve_current(self):
        bak = self.base / "preserve.mp4.bak"
        current = self.base / "preserve.mp4"
        bak.write_text("backup_content", encoding="utf-8")
        current.write_text("current_content", encoding="utf-8")

        success, preserved = mnemosyne.restore_backup_with_mode(bak, mode="restore_and_preserve_current")
        self.assertTrue(success)
        self.assertIsNotNone(preserved)
        self.assertTrue(preserved.exists())
        self.assertEqual(preserved.read_text(encoding="utf-8"), "current_content")
        self.assertTrue(current.exists())
        self.assertEqual(current.read_text(encoding="utf-8"), "backup_content")
        self.assertFalse(bak.exists())

    def test_restore_backup_mode_overwrite_current(self):
        bak = self.base / "overwrite.mp4.bak"
        current = self.base / "overwrite.mp4"
        bak.write_text("backup_content", encoding="utf-8")
        current.write_text("current_content", encoding="utf-8")

        success, preserved = mnemosyne.restore_backup_with_mode(bak, mode="overwrite_current")
        self.assertTrue(success)
        self.assertTrue(current.exists())
        self.assertEqual(current.read_text(encoding="utf-8"), "backup_content")
        self.assertFalse(bak.exists())
        # Preserved file should have been cleaned up after overwrite
        if preserved:
            self.assertFalse(preserved.exists())

    def test_restore_rollback_when_backup_rename_fails(self):
        bak = self.base / "rollback.mp4.bak"
        current = self.base / "rollback.mp4"
        bak.write_text("backup_content", encoding="utf-8")
        current.write_text("current_content", encoding="utf-8")

        # Simulate exception during backup.rename(source)
        orig_rename = Path.rename

        def failing_rename(self_path, target_path):
            if str(self_path) == str(bak):
                raise OSError("Simulated disk error during backup restoration")
            return orig_rename(self_path, target_path)

        with patch.object(Path, "rename", side_effect=failing_rename, autospec=True):
            success, preserved = mnemosyne.restore_backup_with_mode(bak, mode="restore_and_preserve_current")

        self.assertFalse(success)
        # Current file must have been rolled back to original location
        self.assertTrue(current.exists())
        self.assertEqual(current.read_text(encoding="utf-8"), "current_content")


if __name__ == "__main__":
    unittest.main()
