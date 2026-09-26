from __future__ import annotations

import io
import os
import random
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import mnemosyne


class FakeTerminal(io.StringIO):
    def __init__(self, isatty=True, encoding="utf-8"):
        super().__init__()
        self._isatty = isatty
        self._encoding = encoding

    def isatty(self):
        return self._isatty

    @property
    def encoding(self):
        return self._encoding


class MultiWorkerUICollapseTests(unittest.TestCase):
    """Detects and prevents multi-worker layout collapse, ASCII tearing, line wrapping, and terminal scroll overflow."""

    def setUp(self):
        self.orig_stdout = sys.stdout
        self.stream = FakeTerminal(isatty=True, encoding="utf-8")
        sys.stdout = self.stream
        mnemosyne.worker_stats.stats.clear()
        mnemosyne.worker_stats.starts.clear()
        mnemosyne.DISPLAY_STATE["last_compact_at"] = 0.0
        mnemosyne.DISPLAY_STATE["last_compact_snapshot"] = ""
        mnemosyne.DISPLAY_STATE["mode"] = "none"

    def tearDown(self):
        sys.stdout = self.orig_stdout
        mnemosyne.worker_stats.stats.clear()
        mnemosyne.worker_stats.starts.clear()
        mnemosyne.DISPLAY_STATE["last_compact_at"] = 0.0
        mnemosyne.DISPLAY_STATE["last_compact_snapshot"] = ""
        mnemosyne.DISPLAY_STATE["mode"] = "none"

    def _populate_workers(self, count):
        mnemosyne.worker_stats.stats.clear()
        mnemosyne.worker_stats.starts.clear()
        for wid in range(1, count + 1):
            mnemosyne.worker_stats.update(
                wid,
                f"sample_long_movie_name_worker_{wid}.mp4",
                (wid * 11.5) % 100,
                f"{random.randint(24, 60)}",
                f"{random.uniform(1.2, 3.8):.1f}X",
                f"{wid * 50}MB -> {wid * 15}MB (-70%)",
            )

    def test_vertical_line_budget_never_exceeds_terminal_height(self):
        """CRITICAL: Rendered live frame lines must never exceed terminal rows (prevents terminal scroll and ghosting)."""
        config = {
            "target_height": 480,
            "target_fps": 30,
            "video_bitrate": "800k",
            "max_workers": 8,
        }

        worker_counts = [1, 2, 4, 8, 16, 32]
        # Heights: from tight 18 lines to standard 24, 30, 40, 60 lines
        terminal_heights = [18, 20, 24, 30, 40, 60]

        for w_count in worker_counts:
            self._populate_workers(w_count)
            for rows in terminal_heights:
                cols = 80
                with self.subTest(workers=w_count, rows=rows):
                    self.stream.truncate(0)
                    self.stream.seek(0)
                    mnemosyne.DISPLAY_STATE["last_compact_at"] = 0.0
                    mnemosyne.DISPLAY_STATE["last_compact_snapshot"] = ""

                    with patch.object(mnemosyne, "get_terminal_dimensions", return_value=(cols, rows)):
                        mnemosyne.update_display(
                            total=50,
                            completed=10,
                            codec_name="h264_nvenc",
                            config=config,
                        )

                    output = self.stream.getvalue()
                    self.assertTrue(len(output) > 0)

                    # In live mode (output contains ANSI clear/home sequences)
                    if "\033[H" in output:
                        # Strip ANSI and count distinct lines
                        clean_frame = mnemosyne.strip_ansi(output)
                        lines = [line for line in clean_frame.splitlines() if line.strip()]
                        self.assertLessEqual(
                            len(lines),
                            rows,
                            f"Live frame has {len(lines)} lines, exceeding terminal height {rows} (will cause scrolling and tearing!)"
                        )

    def test_horizontal_line_width_never_exceeds_terminal_columns(self):
        """CRITICAL: Every line in multi-worker display must be <= terminal cols (prevents line wrapping and broken ASCII borders)."""
        config = {
            "target_height": 720,
            "target_fps": 60,
            "video_bitrate": "1800k",
            "max_workers": 6,
        }

        self._populate_workers(6)
        terminal_widths = [68, 70, 75, 80, 100, 120, 160]

        for cols in terminal_widths:
            rows = 30
            with self.subTest(cols=cols):
                self.stream.truncate(0)
                self.stream.seek(0)
                mnemosyne.DISPLAY_STATE["last_compact_at"] = 0.0
                mnemosyne.DISPLAY_STATE["last_compact_snapshot"] = ""

                with patch.object(mnemosyne, "get_terminal_dimensions", return_value=(cols, rows)):
                    mnemosyne.update_display(
                        total=20,
                        completed=5,
                        codec_name="libx264",
                        config=config,
                    )

                output = self.stream.getvalue()
                clean_output = mnemosyne.strip_ansi(output)
                lines = clean_output.splitlines()

                for line_idx, line in enumerate(lines):
                    self.assertLessEqual(
                        len(line),
                        cols,
                        f"Line {line_idx} width ({len(line)}) exceeds cols {cols}: '{line}' (causes line wrap and ASCII collapse!)"
                    )

    def test_multiworker_rapid_churn_no_flicker_crash(self):
        """Simulates rapid worker completion and spawning under continuous display refresh."""
        config = {
            "target_height": 480,
            "target_fps": 30,
            "video_bitrate": "800k",
            "max_workers": 8,
        }

        # Rapidly update worker states 100 times with random permutations
        for step in range(100):
            active_count = random.randint(1, 8)
            self._populate_workers(active_count)
            self.stream.truncate(0)
            self.stream.seek(0)
            mnemosyne.DISPLAY_STATE["last_compact_at"] = 0.0

            with patch.object(mnemosyne, "get_terminal_dimensions", return_value=(80, 24)):
                mnemosyne.update_display(
                    total=100,
                    completed=step,
                    codec_name="libx264",
                    config=config,
                )

            output = self.stream.getvalue()
            self.assertTrue(len(output) > 0)
            if "\033[H" in output:
                clean_frame = mnemosyne.strip_ansi(output)
                lines = [l for l in clean_frame.splitlines() if l.strip()]
                self.assertLessEqual(len(lines), 24)


if __name__ == "__main__":
    unittest.main()
