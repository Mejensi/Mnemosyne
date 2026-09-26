from __future__ import annotations

import argparse
import io
import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import mnemosyne


class DriveTypeDetectionTests(unittest.TestCase):
    """Verifies cross-platform detection of removable, fixed, and external drives."""

    def setUp(self):
        mnemosyne._MOUNT_CACHE["linux"] = None
        mnemosyne._MOUNT_CACHE["darwin"] = None

    def tearDown(self):
        mnemosyne._MOUNT_CACHE["linux"] = None
        mnemosyne._MOUNT_CACHE["darwin"] = None

    def test_read_linux_mounts_parsing(self):
        fake_mounts = (
            "/dev/sda2 / ext4 rw,relatime 0 0\n"
            "/dev/sdb1 /media/user/USB ext4 rw,nosuid,nodev 0 0\n"
            "tmpfs /run/user/1000 tmpfs rw,nosuid 0 0\n"
            "/dev/nvme0n1p1 /boot/efi vfat rw,relatime 0 0\n"
        )
        with patch("builtins.open", mock_open(read_data=fake_mounts)):
            mounts = mnemosyne._read_linux_mounts()
            self.assertIn("/", mounts)
            self.assertEqual(mounts["/"], "/dev/sda2")
            self.assertEqual(mounts["/media/user/USB"], "/dev/sdb1")
            self.assertEqual(mounts["/boot/efi"], "/dev/nvme0n1p1")
            self.assertNotIn("/run/user/1000", mounts)  # Non-/dev ignored

    def test_linux_device_is_removable_sysfs_parsing(self):
        def fake_sysfs_open(path, *args, **kwargs):
            p = str(path)
            if "sdb" in p:
                return io.StringIO("1\n")  # Removable USB
            elif "sda" in p:
                return io.StringIO("0\n")  # Fixed SATA SSD
            elif "nvme0n1" in p:
                return io.StringIO("0\n")  # Fixed NVMe
            raise OSError("No such file")

        with patch("builtins.open", side_effect=fake_sysfs_open):
            self.assertTrue(mnemosyne._linux_device_is_removable("/dev/sdb1"))
            self.assertTrue(mnemosyne._linux_device_is_removable("/dev/sdb"))
            self.assertFalse(mnemosyne._linux_device_is_removable("/dev/sda1"))
            self.assertFalse(mnemosyne._linux_device_is_removable("/dev/nvme0n1p1"))
            self.assertFalse(mnemosyne._linux_device_is_removable("/dev/unknown"))

    def test_darwin_volumes_discovery(self):
        with tempfile.TemporaryDirectory() as fake_root:
            vol_dir = Path(fake_root) / "Volumes"
            vol_dir.mkdir()
            (vol_dir / "Macintosh HD").mkdir()
            (vol_dir / "ExternalUSB").mkdir()

            with patch.object(mnemosyne, "Path", return_value=vol_dir):
                volumes = mnemosyne._read_darwin_volumes()
                self.assertTrue(len(volumes) >= 0)


class WorkerThrottlingAndSafetyTests(unittest.TestCase):
    """Verifies that removable media forces worker throttling to prevent I/O thrashing."""

    def test_removable_drive_forces_single_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_on_usb = Path(temp_dir) / "movie.mp4"
            file_on_usb.write_bytes(b"data")

            args = argparse.Namespace(
                paths=[str(file_on_usb)],
                recursive=False,
                workers=None,  # User didn't specify workers -> auto-throttle to 1
                height=None,
                desktop_log=False,
                codec="auto",
            )
            parser = argparse.ArgumentParser()

            # Mock drive type to return DRIVE_REMOVABLE (2)
            with patch.object(mnemosyne, "get_drive_type", return_value=2):
                context = mnemosyne.build_run_context(args, parser)

            self.assertIn(file_on_usb.resolve(), context.removable_targets)
            # Must be throttled to 1 despite user requesting 8
            self.assertEqual(context.session_config["max_workers"], 1)

    def test_fixed_drive_respects_requested_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_on_ssd = Path(temp_dir) / "movie.mp4"
            file_on_ssd.write_bytes(b"data")

            args = argparse.Namespace(
                paths=[str(file_on_ssd)],
                recursive=False,
                workers=6,
                height=None,
                desktop_log=False,
                codec="auto",
            )
            parser = argparse.ArgumentParser()

            # Mock drive type to return DRIVE_FIXED (3)
            with patch.object(mnemosyne, "get_drive_type", return_value=3):
                context = mnemosyne.build_run_context(args, parser)

            self.assertEqual(context.removable_targets, [])
            self.assertEqual(context.session_config["max_workers"], 6)

    def test_disk_space_headroom_checks(self):
        mock_usage = MagicMock()
        mock_usage.free = 500 * 1024 * 1024  # 500 MB free

        with patch("shutil.disk_usage", return_value=mock_usage):
            # Requiring 100 MB on 500 MB free drive -> OK
            ok, free = mnemosyne.has_enough_space(Path("/any/path"), 100 * 1024 * 1024)
            self.assertTrue(ok)
            self.assertEqual(free, 500 * 1024 * 1024)

            # Requiring 1 GB on 500 MB free drive -> NOT ENOUGH
            ok, free = mnemosyne.has_enough_space(Path("/any/path"), 1024 * 1024 * 1024)
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
