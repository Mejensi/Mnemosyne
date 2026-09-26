from __future__ import annotations

import math
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import mnemosyne


class WorkerStatsAndETAEnhancementTests(unittest.TestCase):
    """Verifies EMA smoothed ETA, queue-level ETA calculation, and stage detail tracking."""

    def setUp(self):
        self.stats = mnemosyne.WorkerStats()

    def test_format_speed_label(self):
        self.assertEqual(mnemosyne.format_speed_label("3.91x"), "Speed: 3.9x")
        self.assertEqual(mnemosyne.format_speed_label("12.5X"), "Speed: 12.5x")
        self.assertEqual(mnemosyne.format_speed_label("0X"), "...")
        self.assertEqual(mnemosyne.format_speed_label("-"), "...")
        self.assertEqual(mnemosyne.format_speed_label(""), "...")
        self.assertEqual(mnemosyne.format_speed_label(None), "...")

    def test_format_fps_label(self):
        self.assertEqual(mnemosyne.format_fps_label("117.29"), "117 FPS")
        self.assertEqual(mnemosyne.format_fps_label("60"), "60 FPS")
        self.assertEqual(mnemosyne.format_fps_label("0"), "...")
        self.assertEqual(mnemosyne.format_fps_label("-"), "...")
        self.assertEqual(mnemosyne.format_fps_label(None), "...")

    def test_format_eta(self):
        self.assertEqual(mnemosyne.format_eta(0), "0s")
        self.assertEqual(mnemosyne.format_eta(45), "45s")
        self.assertEqual(mnemosyne.format_eta(65), "1m 05s")
        self.assertEqual(mnemosyne.format_eta(310), "5m 10s")
        self.assertEqual(mnemosyne.format_eta(3665), "1h 01m")
        self.assertEqual(mnemosyne.format_eta(7320), "2h 02m")
        self.assertEqual(mnemosyne.format_eta(None), "estimating...")
        self.assertEqual(mnemosyne.format_eta(-5), "estimating...")
        self.assertEqual(mnemosyne.format_eta(float("nan")), "estimating...")
        self.assertEqual(mnemosyne.format_eta(float("inf")), "estimating...")

    def test_worker_stats_ema_eta_smoothing(self):
        # Initial update
        self.stats.update(1, "sample.mp4", 0.0, "30", "1.0X", stage="Initializing")
        data = self.stats.get_all()[1]
        self.assertEqual(data["stage"], "Initializing")
        self.assertIsNone(data["eta_seconds"])

        # Progress simulation over time
        t0 = time.time()
        self.stats.starts[1] = t0 - 10.0
        self.stats.history[1] = [(t0 - 10.0, 10.0), (t0 - 5.0, 30.0)]
        self.stats.update(1, "sample.mp4", 50.0, "60", "2.0x", stage="Encoding", stage_detail="50.0%")
        
        updated_data = self.stats.get_all()[1]
        self.assertEqual(updated_data["stage"], "Encoding")
        self.assertEqual(updated_data["stage_detail"], "50.0%")
        self.assertIsNotNone(updated_data["eta_seconds"])
        self.assertGreater(updated_data["eta_seconds"], 0)

    def test_queue_eta_calculation(self):
        # Empty queue or total completed
        self.assertEqual(self.stats.get_queue_eta_formatted(10, 10), "0s")
        self.assertEqual(self.stats.get_queue_eta_formatted(0, 0), "0s")

        # Record completed file durations (e.g. average 20 seconds per video)
        self.stats.record_completed(1, 20.0)
        self.stats.record_completed(2, 20.0)

        # 5 remaining tasks with 2 active workers -> (5 * 20s) / 2 = 50s
        self.stats.update(1, "active1.mp4", 50.0, "30", "1.0x")
        self.stats.update(2, "active2.mp4", 50.0, "30", "1.0x")

        eta_formatted = self.stats.get_queue_eta_formatted(total=7, completed=2)
        self.assertEqual(eta_formatted, "50s")


class UIRenderingAndArtifactEliminationTests(unittest.TestCase):
    """Verifies that live dashboard rendering clears lines properly without trailing artifacts."""

    def test_render_progress_stages_and_labels(self):
        # Encoding stage
        rendered_enc = mnemosyne.render_progress(
            label="movie.mp4",
            percent=43.5,
            fps="121.47",
            speed="4.0x",
            size_stats="",
            eta="16m 47s",
            stage="Encoding",
            stage_detail="43.5%",
        )
        self.assertIn("Speed: 4.0x", rendered_enc)
        self.assertIn("121 FPS", rendered_enc)
        self.assertIn("ETA: 16m 47s", rendered_enc)
        self.assertIn("[Encoding: 43.5%]", rendered_enc)

        # Verifying stage
        rendered_ver = mnemosyne.render_progress(
            label="movie.mp4",
            percent=99.9,
            fps="120",
            speed="1.0x",
            size_stats="",
            eta="~3s",
            stage="Verifying",
            stage_detail="Frame Decode Integrity",
        )
        self.assertIn("[Verifying: Frame Decode Integrity]", rendered_ver)
        self.assertIn("ETA: ~3s", rendered_ver)

        # Safety Swap stage
        rendered_swap = mnemosyne.render_progress(
            label="movie.mp4",
            percent=100.0,
            fps="-",
            speed="-",
            size_stats="100MB -> 35MB (65% saved)",
            eta="~1s",
            stage="Safety Swap",
            stage_detail="Restoring Timestamps",
        )
        self.assertIn("[Safety Swap: Restoring Timestamps]", rendered_swap)

        # Completed stage
        rendered_done = mnemosyne.render_progress(
            label="movie.mp4",
            percent=100.0,
            fps="0",
            speed="0",
            size_stats="100MB -> 35MB (65% saved)",
            eta="",
            stage="Done",
            stage_detail="Completed",
        )
        self.assertIn("DONE", rendered_done)
        self.assertIn("[Completed]", rendered_done)

    def test_render_live_dashboard_erases_trailing_line_artifacts(self):
        # Ensure render_live_dashboard appends \033[K to every line
        captured = []

        class FakeStream:
            def write(self, data):
                captured.append(data)
            def flush(self):
                pass

        with patch("sys.stdout", FakeStream()), patch.dict(mnemosyne.DISPLAY_STATE, {"mode": "live"}):
            frame = "Line 1 with text\nLine 2 with text"
            mnemosyne.render_live_dashboard(frame)
            output = "".join(captured)
            # Must contain \033[K before newlines to erase trailing characters from previous renders
            self.assertIn("\033[K\n", output)
            self.assertIn("\033[J", output)


class HardwareSafeWorkerAllocationTests(unittest.TestCase):
    """Verifies safe default worker limits and process priority kwargs."""

    def test_get_safe_default_workers_gpu(self):
        # On multi-core systems, GPU encoder must be capped to safe 2 workers max
        workers = mnemosyne.get_safe_default_workers("h264_nvenc")
        self.assertLessEqual(workers, 2)

        workers_amf = mnemosyne.get_safe_default_workers("h264_amf")
        self.assertLessEqual(workers_amf, 2)

        workers_qsv = mnemosyne.get_safe_default_workers("h264_qsv")
        self.assertLessEqual(workers_qsv, 2)

    def test_get_safe_default_workers_cpu(self):
        workers_cpu = mnemosyne.get_safe_default_workers("libx264")
        self.assertLessEqual(workers_cpu, 3)

    def test_get_safe_default_workers_removable(self):
        # Removable drives must always be 1 worker
        self.assertEqual(mnemosyne.get_safe_default_workers("auto", is_removable=True), 1)

    def test_get_background_process_kwargs(self):
        kwargs = mnemosyne.get_background_process_kwargs()
        if mnemosyne.IS_WINDOWS:
            self.assertIn("creationflags", kwargs)
            # Must include below normal priority class (0x4000)
            self.assertTrue(kwargs["creationflags"] & 0x4000)
        else:
            self.assertIn("preexec_fn", kwargs)
            self.assertTrue(callable(kwargs["preexec_fn"]))


if __name__ == "__main__":
    unittest.main()
