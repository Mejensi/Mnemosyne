from __future__ import annotations

import io
import math
import os
import random
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import mnemosyne


class FakeTerminalStream(io.StringIO):
    def __init__(self, isatty=True, encoding="utf-8"):
        super().__init__()
        self._isatty = isatty
        self._encoding = encoding

    def isatty(self):
        return self._isatty

    @property
    def encoding(self):
        return self._encoding


class TerminalDimensionMatrixTests(unittest.TestCase):
    """Verifies UI rendering stability across an exhaustive matrix of terminal geometries."""

    def setUp(self):
        self.orig_stdout = sys.stdout
        self.stream = FakeTerminalStream(isatty=True, encoding="utf-8")
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

    def test_rendering_across_dimension_grid(self):
        cols_matrix = [20, 35, 40, 44, 60, 67, 68, 70, 80, 100, 140, 200]
        rows_matrix = [5, 10, 13, 14, 20, 24, 40, 60]

        config = {
            "target_height": 480,
            "target_fps": 30,
            "video_bitrate": "800k",
            "max_workers": 4,
        }

        # Populate sample worker stats
        for wid in range(1, 5):
            mnemosyne.worker_stats.update(
                wid,
                f"clip_{wid}.mp4",
                25.0 * wid,
                "60",
                "2.5X",
                "10MB -> 3MB (-70%)",
            )

        for cols in cols_matrix:
            for rows in rows_matrix:
                with self.subTest(cols=cols, rows=rows):
                    self.stream.truncate(0)
                    self.stream.seek(0)
                    mnemosyne.DISPLAY_STATE["last_compact_at"] = 0.0
                    mnemosyne.DISPLAY_STATE["last_compact_snapshot"] = ""
                    with patch.object(mnemosyne, "get_terminal_dimensions", return_value=(cols, rows)):
                        # update_display must never raise an exception for any terminal dimension
                        mnemosyne.update_display(
                            total=10,
                            completed=2,
                            codec_name="libx264",
                            config=config,
                        )
                        output = self.stream.getvalue()
                        self.assertTrue(len(output) > 0)

    def test_box_line_boundary_invariants(self):
        """Ensures header box lines maintain visual width integrity and do not spill."""
        config = {
            "target_height": 720,
            "target_fps": 60,
            "video_bitrate": "1800k",
            "max_workers": 2,
        }
        for width in [44, 50, 70, 100, 120]:
            header = mnemosyne.draw_header(config, "h264_nvenc", width=width)
            lines = header.splitlines()
            self.assertGreater(len(lines), 5)
            # The top border, separators, and box lines must all match exactly (width + 5)
            for line in lines:
                visible = mnemosyne.strip_ansi(line)
                self.assertEqual(
                    len(visible),
                    width + 5,
                    f"Line '{visible}' width ({len(visible)}) mismatch for target width {width}",
                )


class ContentFuzzingAndEdgeCasesTests(unittest.TestCase):
    """Verifies that arbitrary, malicious, or malformed inputs do not crash or corrupt the UI."""

    def setUp(self):
        self.orig_stdout = sys.stdout
        self.stream = FakeTerminalStream(isatty=True, encoding="utf-8")
        sys.stdout = self.stream

    def tearDown(self):
        sys.stdout = self.orig_stdout

    def test_ellipsize_text_robustness(self):
        edge_cases = [
            ("", 10, ""),
            (None, 10, ""),
            ("normal_text.mp4", 5, "no..."),
            ("short", 10, "short"),
            ("exact10len", 10, "exact10len"),
            ("exact11len!", 10, "exact11..."),
            ("abc", 0, "a"),
            ("abc", 1, "a"),
            ("abc", 2, "ab"),
            ("abc", 3, "abc"),
            ("multiline\ntext\rwith\nnewlines", 30, "multiline text with newlines"),
            ("a" * 1000, 20, "a" * 17 + "..."),
            ("🎬🍿🎥 Türkce Karakterler 🚀", 12, "🎬🍿🎥 Türkc..."),
        ]
        for inp, width, expected in edge_cases:
            res = mnemosyne.ellipsize_text(inp, width)
            self.assertEqual(
                res,
                expected,
                f"Failed for input={inp!r}, width={width!r}. Got: {res!r}",
            )

    def test_render_progress_anomalous_percentages(self):
        """Verifies render_progress clamps anomalous percentages gracefully."""
        cases = [
            (-100.0, "primary or error bar without negative repeats"),
            (-0.001, "zero clamp"),
            (0.0, "zero bar"),
            (50.0, "half bar"),
            (99.99, "near complete"),
            (100.0, "complete DONE"),
            (150.0, "overflow clamp to 100%"),
            (float("nan"), "nan handling"),
            (float("inf"), "inf handling"),
            ("invalid_str", "string fallback"),
        ]
        for pct, desc in cases:
            with self.subTest(pct=pct, desc=desc):
                out = mnemosyne.render_progress(
                    label="extreme_test.mp4",
                    percent=pct,
                    fps="120",
                    speed="4.0X",
                    size_stats="100MB -> 20MB",
                    eta="ETA: 1m 0s",
                    label_width=20,
                    bar_width=30,
                )
                self.assertIsInstance(out, str)
                self.assertNotIn("ValueError", out)
                # Verify glyph count doesn't blow out
                visible = mnemosyne.strip_ansi(out)
                lines = visible.splitlines()
                self.assertLessEqual(len(lines), 3)

    def test_render_progress_none_fields(self):
        """Verifies render_progress does not fail when stats fields are None or empty."""
        out = mnemosyne.render_progress(
            label=None,
            percent=33.3,
            fps=None,
            speed=None,
            size_stats=None,
            eta=None,
            label_width=15,
            bar_width=20,
        )
        self.assertIsInstance(out, str)
        self.assertIn("33.3%", out)


class EncodingAndGlyphFallbackTests(unittest.TestCase):
    """Verifies that ASCII-only terminals correctly fall back without UnicodeEncodeError."""

    def test_ascii_fallback_glyphs_and_boxes(self):
        with patch.object(mnemosyne, "supports_unicode_output", return_value=False):
            box = mnemosyne.get_box_chars()
            self.assertEqual(box["tl"], "+")
            self.assertEqual(box["v"], "|")
            self.assertEqual(box["h"], "-")

            glyphs = mnemosyne.get_progress_glyphs()
            self.assertEqual(glyphs, ("#", "-", "OK", ">", "|-"))

            warn = mnemosyne.get_warning_symbol()
            self.assertEqual(warn, "WARNING")

            tickers = mnemosyne.get_ticker_messages()
            for msg in tickers:
                # All messages in ASCII ticker must be encodable to ASCII
                msg.encode("ascii")

    def test_draw_header_ascii_encodable(self):
        config = {
            "target_height": 480,
            "target_fps": 30,
            "video_bitrate": "800k",
            "max_workers": 2,
        }
        with patch.object(mnemosyne, "supports_unicode_output", return_value=False):
            header = mnemosyne.draw_header(config, "libx264", width=50)
            # Must encode to pure ASCII without error
            header.encode("ascii")

    def test_render_progress_ascii_encodable(self):
        with patch.object(mnemosyne, "supports_unicode_output", return_value=False):
            progress_running = mnemosyne.render_progress(
                "video.mp4", 45.0, "30", "1.5X", "50MB -> 20MB", "ETA: 10s"
            )
            progress_done = mnemosyne.render_progress(
                "video.mp4", 100.0, "30", "1.5X", "50MB -> 10MB (-80%)"
            )
            progress_running.encode("ascii")
            progress_done.encode("ascii")


class ConcurrentRenderingThreadSafetyTests(unittest.TestCase):
    """Stress tests WorkerStats and display routines under heavy multithreaded contention."""

    def test_worker_stats_high_concurrency(self):
        stats = mnemosyne.WorkerStats()
        stop_flag = threading.Event()
        errors = []

        def worker_loop(wid):
            counter = 0
            while not stop_flag.is_set():
                counter += 1
                pct = (counter % 100) + random.random()
                stats.update(
                    wid,
                    f"stream_{wid}_{counter}.mp4",
                    pct,
                    f"{random.randint(20, 120)}",
                    f"{random.uniform(0.5, 5.0):.1f}X",
                    f"{counter}MB",
                )
                if counter % 7 == 0:
                    stats.remove_worker(wid)
                time.sleep(0.001)

        def reader_loop():
            for _ in range(50):
                try:
                    all_stats = stats.get_all()
                    for wid, data in all_stats.items():
                        _ = data["fn"], data["pct"], data["fps"]
                    time.sleep(0.002)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker_loop, args=(i,)) for i in range(8)]
        reader = threading.Thread(target=reader_loop)

        for t in threads:
            t.start()
        reader.start()

        reader.join()
        stop_flag.set()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread safety errors occurred: {errors}")


class NonInteractiveAndPipedDisplayTests(unittest.TestCase):
    """Verifies that non-interactive / redirected streams produce throttled, clean compact output."""

    def test_piped_output_uses_compact_mode_without_ansi_clears(self):
        fake_stdout = FakeTerminalStream(isatty=False, encoding="utf-8")
        orig_stdout = sys.stdout
        sys.stdout = fake_stdout
        try:
            config = {
                "target_height": 480,
                "target_fps": 30,
                "video_bitrate": "800k",
                "max_workers": 1,
            }
            # Set state to ensure clean start
            mnemosyne.DISPLAY_STATE["last_compact_at"] = 0
            mnemosyne.DISPLAY_STATE["last_compact_snapshot"] = ""
            mnemosyne.DISPLAY_STATE["mode"] = "none"

            mnemosyne.worker_stats.update(1, "piped_test.mp4", 50.0, "30", "1.0X")

            with patch.object(mnemosyne, "supports_live_dashboard", return_value=False):
                mnemosyne.update_display(total=1, completed=0, codec_name="libx264", config=config)

            output = fake_stdout.getvalue()
            self.assertIn("[Progress]", output)
            self.assertIn("piped_test.mp4", output)
            # Piped mode must NOT emit terminal clearing escape sequence
            self.assertNotIn("\033[2J", output)
            self.assertNotIn("\033[H", output)
        finally:
            sys.stdout = orig_stdout


class InteractivePromptResilienceTests(unittest.TestCase):
    """Verifies that interactive prompts handle EOF, invalid inputs, and interruptions safely."""

    def test_prompt_menu_choice_recovery_on_invalid_and_eof(self):
        inputs = iter(["invalid_1", "invalid_2", ""])
        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("sys.stdout", new_callable=io.StringIO):
            choice = mnemosyne.prompt_menu_choice("Choose: ", "default_val", ["valid1", "default_val"])
            self.assertEqual(choice, "default_val")

    def test_prompt_menu_choice_on_immediate_eof_error(self):
        with patch("builtins.input", side_effect=EOFError), \
             patch("sys.stdout", new_callable=io.StringIO):
            choice = mnemosyne.prompt_menu_choice("Choose: ", "default_val", ["valid1", "default_val"])
            self.assertEqual(choice, "default_val")


if __name__ == "__main__":
    unittest.main()
