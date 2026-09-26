from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import mnemosyne


class EmptyScanFlowTests(unittest.TestCase):
    """Verifies subfolder probing, recursive upgrade prompts, and empty folder handling."""

    def test_probe_subfolder_videos_detection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sub1 = root / "Movies"
            sub2 = root / "Clips" / "Vacation"
            sub1.mkdir(parents=True)
            sub2.mkdir(parents=True)

            vid1 = sub1 / "movie.mp4"
            vid2 = sub2 / "clip.mkv"
            vid1.touch()
            vid2.touch()

            args = argparse.Namespace(
                paths=[str(root)],
                recursive=False,
                workers=1,
                height=None,
                desktop_log=False,
                codec="auto",
            )
            parser = argparse.ArgumentParser()
            context = mnemosyne.build_run_context(args, parser)

            # Root has 0 videos in non-recursive scan
            videos, _, _ = mnemosyne.scan_videos_for_context(context)
            self.assertEqual(videos, [])

            # probe_subfolder_videos must find the 2 nested videos
            sub_videos = mnemosyne.probe_subfolder_videos(context)
            self.assertEqual(len(sub_videos), 2)
            self.assertIn(vid1.resolve(), [v.resolve() for v in sub_videos])
            self.assertIn(vid2.resolve(), [v.resolve() for v in sub_videos])

    def test_probe_subfolder_videos_returns_empty_when_already_recursive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sub = root / "Sub"
            sub.mkdir()
            (sub / "clip.mp4").touch()

            args = argparse.Namespace(
                paths=[str(root)],
                recursive=True,
                workers=1,
                height=None,
                desktop_log=False,
                codec="auto",
            )
            context = mnemosyne.build_run_context(args, argparse.ArgumentParser())
            self.assertEqual(mnemosyne.probe_subfolder_videos(context), [])

    def test_main_subfolder_prompt_enables_recursive_scan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sub = root / "Nested"
            sub.mkdir()
            vid = sub / "nested_movie.mp4"
            vid.touch()

            argv_backup = sys.argv[:]
            inputs = iter(["y", "q"])  # 1st input: 'y' to enable recursive, 2nd input: 'q' at ready prompt
            try:
                sys.argv = ["mnemosyne.py", str(root)]
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(mnemosyne, "supports_interactive_input", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "show_security_notice"))
                    stack.enter_context(patch.object(mnemosyne, "prompt_stale_ffmpeg_cleanup"))
                    stack.enter_context(patch.object(mnemosyne, "ensure_ffmpeg", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "detect_gpu_codec", return_value=("libx264", "CPU (x264)")))
                    stack.enter_context(patch.object(mnemosyne, "audit_orphaned_backups", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "clear_screen"))
                    stack.enter_context(patch.object(mnemosyne, "draw_logo", return_value="logo"))
                    stack.enter_context(patch.object(mnemosyne, "render_run_summary"))
                    stack.enter_context(patch("builtins.input", side_effect=lambda prompt="": next(inputs)))

                    with contextlib.redirect_stdout(io.StringIO()) as captured_out:
                        result = mnemosyne.main()

                    output = captured_out.getvalue()
                    self.assertIn("Found 1 video(s) inside subfolders", output)
                    self.assertEqual(result, 0)
            finally:
                sys.argv = argv_backup

    def test_main_subfolder_prompt_quit_choice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sub = root / "Nested"
            sub.mkdir()
            (sub / "nested_movie.mp4").touch()

            argv_backup = sys.argv[:]
            inputs = iter(["q"])  # User chooses 'q' to quit when asked about subfolders
            try:
                sys.argv = ["mnemosyne.py", str(root)]
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(mnemosyne, "supports_interactive_input", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "show_security_notice"))
                    stack.enter_context(patch.object(mnemosyne, "prompt_stale_ffmpeg_cleanup"))
                    stack.enter_context(patch.object(mnemosyne, "ensure_ffmpeg", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "detect_gpu_codec", return_value=("libx264", "CPU (x264)")))
                    stack.enter_context(patch.object(mnemosyne, "audit_orphaned_backups", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "clear_screen"))
                    stack.enter_context(patch.object(mnemosyne, "draw_logo", return_value="logo"))
                    stack.enter_context(patch("builtins.input", side_effect=lambda prompt="": next(inputs)))

                    with contextlib.redirect_stdout(io.StringIO()) as captured_out:
                        result = mnemosyne.main()

                    self.assertEqual(result, 0)
            finally:
                sys.argv = argv_backup


if __name__ == "__main__":
    unittest.main()
