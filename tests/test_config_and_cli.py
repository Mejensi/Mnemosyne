from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mnemosyne


class ConfigNormalizationAndMigrationTests(unittest.TestCase):
    """Verifies schema validation, normalization, and migration of user configuration files."""

    def test_normalize_empty_or_none_returns_defaults(self):
        normalized = mnemosyne.normalize_saved_config(None)
        self.assertEqual(normalized["profile_id"], mnemosyne.DEFAULT_PROFILE_ID)
        self.assertEqual(normalized["target_height"], 480)
        self.assertEqual(normalized["video_bitrate"], "800k")
        self.assertEqual(normalized["audio_bitrate"], "128k")

    def test_normalize_profile_selection(self):
        # Setting profile_id = "720p" should load 720p parameters
        cfg = mnemosyne.normalize_saved_config({"profile_id": "720p"})
        self.assertEqual(cfg["profile_id"], "720p")
        self.assertEqual(cfg["target_height"], 720)
        self.assertEqual(cfg["video_bitrate"], "1800k")
        self.assertEqual(cfg["audio_bitrate"], "160k")

        # Invalid profile falls back to default
        cfg_invalid = mnemosyne.normalize_saved_config({"profile_id": "invalid_unknown"})
        self.assertEqual(cfg_invalid["profile_id"], mnemosyne.DEFAULT_PROFILE_ID)

    def test_normalize_malformed_and_out_of_bound_values(self):
        corrupted = {
            "max_workers": -10,
            "target_height": "not_a_number",
            "target_fps": -30,
            "sort": "invalid_sort_key",
            "recursive": "true",  # string instead of bool
        }
        normalized = mnemosyne.normalize_saved_config(corrupted)
        # Should gracefully fall back to valid ranges/defaults
        self.assertEqual(normalized["max_workers"], mnemosyne.DEFAULT_CONFIG["max_workers"])
        self.assertEqual(normalized["target_height"], mnemosyne.DEFAULT_CONFIG["target_height"])
        self.assertEqual(normalized["target_fps"], 1)  # clamped to minimum 1
        self.assertEqual(normalized["sort"], mnemosyne.DEFAULT_CONFIG["sort"])
        self.assertTrue(normalized["recursive"])

        # Type errors fall back to DEFAULT_CONFIG
        type_corrupted = {"target_fps": "not_int"}
        self.assertEqual(mnemosyne.normalize_saved_config(type_corrupted)["target_fps"], mnemosyne.DEFAULT_CONFIG["target_fps"])

    def test_save_and_load_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            sample_config = {
                "profile_id": "1080p",
                "max_workers": 2,
                "recursive": True,
            }
            with patch.object(mnemosyne, "APP_CONFIG_FILE", config_file):
                # Save config
                ok = mnemosyne.save_config(sample_config)
                self.assertTrue(ok)
                self.assertTrue(config_file.exists())

                # Load and verify
                loaded = mnemosyne.load_config()
                self.assertEqual(loaded["profile_id"], "1080p")
                self.assertEqual(loaded["target_height"], 1080)
                self.assertEqual(loaded["max_workers"], 2)
                self.assertTrue(loaded["recursive"])


class CommandLineArgumentsTests(unittest.TestCase):
    """Verifies CLI argument parsing, flags, and parameter overrides."""

    def setUp(self):
        self.parser = mnemosyne.build_argument_parser()

    def test_cli_flags_parsing(self):
        args = self.parser.parse_args([
            "-r",
            "-w", "4",
            "--height", "720",
            "--codec", "libx264",
            "--desktop-log",
            "-d",
            "video1.mp4",
            "video2.mkv",
        ])
        self.assertTrue(args.recursive)
        self.assertEqual(args.workers, 4)
        self.assertEqual(args.height, 720)
        self.assertEqual(args.codec, "libx264")
        self.assertTrue(args.desktop_log)
        self.assertTrue(args.debug)
        self.assertEqual(args.paths, ["video1.mp4", "video2.mkv"])

    def test_build_run_context_cli_precedence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_file = Path(temp_dir) / "test.mp4"
            target_file.touch()

            args = self.parser.parse_args([
                "--workers", "3",
                "--height", "1080",
                str(target_file),
            ])

            context = mnemosyne.build_run_context(args, self.parser)
            self.assertEqual(context.mode, "explicit-files")
            self.assertEqual(context.session_config["max_workers"], 3)
            self.assertEqual(context.session_config["target_height"], 1080)
            self.assertEqual(context.input_files, [target_file.resolve()])


class EnumInvariantsAndCompatibilityTests(unittest.TestCase):
    """Verifies that all Enum types maintain strict backwards compatibility with primitives and JSON."""

    def test_process_result_int_invariants(self):
        self.assertIsInstance(mnemosyne.ProcessResult.SUCCESS, int)
        self.assertEqual(mnemosyne.ProcessResult.SUCCESS, 1)
        self.assertEqual(mnemosyne.ProcessResult.SKIPPED, 2)
        self.assertEqual(mnemosyne.ProcessResult.FAILED, 0)
        self.assertEqual(mnemosyne.ProcessResult.FAILED, False)

    def test_drive_type_int_invariants(self):
        self.assertIsInstance(mnemosyne.DriveType.REMOVABLE, int)
        self.assertEqual(mnemosyne.DriveType.REMOVABLE, 2)
        self.assertEqual(mnemosyne.DriveType.FIXED, 3)
        self.assertEqual(mnemosyne.DRIVE_REMOVABLE, mnemosyne.DriveType.REMOVABLE)
        self.assertEqual(mnemosyne.DRIVE_FIXED, mnemosyne.DriveType.FIXED)

    def test_string_enums_invariants(self):
        for member, expected_str in [
            (mnemosyne.StorageMode.PORTABLE, "portable"),
            (mnemosyne.StorageMode.APPDATA, "appdata"),
            (mnemosyne.SortOrder.NAME_AZ, "name_az"),
            (mnemosyne.SystemFFmpegPolicy.PROMPT, "prompt"),
            (mnemosyne.VideoCodec.VAAPI, "h264_vaapi"),
        ]:
            self.assertIsInstance(member, str)
            self.assertEqual(member, expected_str)
            self.assertIn(member, {expected_str})
            self.assertIn(expected_str, {member})

    def test_enums_json_serialization_roundtrip(self):
        payload = {
            "storage": mnemosyne.StorageMode.PORTABLE,
            "sort": mnemosyne.SortOrder.NAME_AZ,
            "policy": mnemosyne.SystemFFmpegPolicy.ALLOW,
            "result": mnemosyne.ProcessResult.SUCCESS,
            "exit": mnemosyne.ExitCode.SUCCESS,
        }
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)
        self.assertEqual(
            decoded,
            {
                "storage": "portable",
                "sort": "name_az",
                "policy": "allow",
                "result": 1,
                "exit": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()

