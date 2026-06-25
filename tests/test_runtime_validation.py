from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]

import mnemosyne


def default_config(**overrides):
    config = mnemosyne.DEFAULT_CONFIG.copy()
    config.update(
        {
            "target_height": 480,
            "video_bitrate": "350k",
            "audio_bitrate": "128k",
            "x264_preset": "ultrafast",
            "ffmpeg_threads": 1,
            "target_fps": 30,
            "max_workers": 1,
            "recursive": False,
            "verify_frames": True,
            "auto_download_ffmpeg": False,
            "desktop_log": False,
            "auto_cleanup": True,
            "show_drive_warnings": True,
            "preserve_metadata": True,
            "system_ffmpeg_policy": "prompt",
        }
    )
    config.update(overrides)
    return config


@contextlib.contextmanager
def pushd(path: Path):
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)

@contextlib.contextmanager
def managed_tempdir(prefix: str):
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        base = Path(temp_dir)
        try:
            yield base
        finally:
            mnemosyne.cleanup_temp_files(base, recursive=True, include_current_session=True)

def make_stale_workspace(base: Path, session_id="stale-session"):
    workspace = base / mnemosyne.TEMP_WORKSPACE_NAME / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / mnemosyne.TEMP_WORKSPACE_MARKER).write_text(
        json.dumps({"app": mnemosyne.APP_NAME, "session_id": session_id}),
        encoding="utf-8",
    )
    (workspace / mnemosyne.TEMP_WORKSPACE_LOCK).write_text("1", encoding="utf-8")
    return workspace

MIN_CACHE_CLIP_BYTES = 256

class FakeStdout(io.StringIO):
    def __init__(self, isatty_result=True, encoding="utf-8"):
        super().__init__()
        self._isatty_result = isatty_result
        self._encoding = encoding

    def isatty(self):
        return self._isatty_result

    @property
    def encoding(self):
        return self._encoding

class MnemosyneRuntimeValidationTests(unittest.TestCase):
    _clip_cache_dir: Path = None

    @classmethod
    def setUpClass(cls):
        if not mnemosyne.check_ffmpeg_with_policy("allow"):
            raise unittest.SkipTest("FFmpeg/FFprobe not available")
        cls.ffmpeg = mnemosyne.FFMPEG_CMD
        cls.ffprobe = mnemosyne.FFPROBE_CMD
        cls._clip_cache_dir = Path(tempfile.gettempdir()) / "mnemo_clip_cache"
        cls._clip_cache_dir.mkdir(parents=True, exist_ok=True)

    def _build_clip(self, cmd, key, dest):
        """Run an ffmpeg lavfi command, caching the result by parameter key.

        Each unique (size, rate, duration, bitrate, ...) combination encodes
        once per process and is then copied into the destination path on every
        subsequent call. This avoids re-running identical lavfi encode work
        across the 25+ test methods in this class.
        """
        cache_path = self._clip_cache_dir / f"{key}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and cache_path.stat().st_size >= MIN_CACHE_CLIP_BYTES:
            shutil.copyfile(cache_path, dest)
            return dest
        self.run_cmd(cmd)
        if dest.exists() and dest.stat().st_size >= MIN_CACHE_CLIP_BYTES:
            try:
                shutil.copyfile(dest, cache_path)
            except OSError:
                pass
        return dest

    def _build_multistream_clip(self, cmd, key, dest):
        cache_path = self._clip_cache_dir / f"{key}.mkv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and cache_path.stat().st_size >= MIN_CACHE_CLIP_BYTES:
            shutil.copyfile(cache_path, dest)
            return dest
        self.run_cmd(cmd)
        if dest.exists() and dest.stat().st_size >= MIN_CACHE_CLIP_BYTES:
            try:
                shutil.copyfile(dest, cache_path)
            except OSError:
                pass
        return dest

    def run_cmd(self, cmd, cwd=None):
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, timeout=20)

    def make_av_clip(
        self,
        path: Path,
        duration=1.0,
        size="640x480",
        rate=30,
        audio_freqs=None,
        pix_fmt="yuv420p",
        video_bitrate="800k",
        audio_sample_rate=44100,
    ):
        audio_freqs = audio_freqs or [440]
        cmd = [self.ffmpeg, "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}"]
        for freq in audio_freqs:
            cmd.extend(["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={audio_sample_rate}"])
        cmd.extend(["-t", str(duration), "-map", "0:v:0"])
        for index, _freq in enumerate(audio_freqs, start=1):
            cmd.extend(["-map", f"{index}:a:0"])
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-threads:v",
                "1",
                "-pix_fmt",
                pix_fmt,
                "-b:v",
                video_bitrate,
                "-c:a",
                "aac",
                "-shortest",
                str(path),
            ]
        )
        key = f"av_{size}_{rate}_{duration}_{pix_fmt}_{video_bitrate}_{'-'.join(map(str, audio_freqs))}_{audio_sample_rate}"
        self._build_clip(cmd, key, path)
        return path

    def make_multistream_clip(self, path: Path, duration=1.0):
        subtitle_path = path.with_name("subtitle_en.srt")
        subtitle_path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n",
            encoding="utf-8",
        )
        cmd = [
            self.ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=44100",
            "-i",
            str(subtitle_path),
            "-t",
            str(duration),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:a:0",
            "-map",
            "3:s:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads:v",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-c:s",
            "srt",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:1",
            "language=tur",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:a:0",
            "title=English Main",
            "-metadata:s:a:1",
            "title=Turkish Alt",
            "-metadata:s:s:0",
            "title=English Subtitle",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "0",
            "-disposition:s:0",
            "default",
            str(path),
        ]
        self._build_multistream_clip(cmd, "multistream_640x360_30_1.0", path)
        return path

    def make_multi_video_clip(
        self,
        path: Path,
        duration=1.0,
        first_size="640x360",
        first_rate=30,
        second_size="640x360",
        second_rate=30,
    ):
        cmd = [
            self.ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={first_size}:rate={first_rate}",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={second_size}:rate={second_rate}",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            str(duration),
            "-map",
            "0:v:0",
            "-map",
            "1:v:0",
            "-map",
            "2:a:0",
            "-c:v:0",
            "libx264",
            "-preset:v:0",
            "ultrafast",
            "-threads:v:0",
            "1",
            "-pix_fmt:v:0",
            "yuv420p",
            "-b:v:0",
            "700k",
            "-c:v:1",
            "libx264",
            "-preset:v:1",
            "ultrafast",
            "-threads:v:1",
            "1",
            "-pix_fmt:v:1",
            "yuv420p",
            "-b:v:1",
            "1600k",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(path),
        ]
        key = f"multivid_{first_size}_{first_rate}_{second_size}_{second_rate}_{duration}"
        self._build_clip(cmd, key, path)
        return path

    def make_chaptered_clip(self, path: Path, duration=1.8):
        raw_path = path.with_name("chapter_source.mp4")
        metadata_path = path.with_name("chapters.ffmeta")
        self.make_av_clip(raw_path, duration=duration)
        metadata_path.write_text(
            ";FFMETADATA1\n"
            "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=900\ntitle=Intro\n"
            "[CHAPTER]\nTIMEBASE=1/1000\nSTART=900\nEND=1800\ntitle=Main\n",
            encoding="utf-8",
        )
        self.run_cmd(
            [
                self.ffmpeg,
                "-y",
                "-i",
                str(raw_path),
                "-f",
                "ffmetadata",
                "-i",
                str(metadata_path),
                "-map",
                "0",
                "-map_metadata",
                "1",
                "-map_chapters",
                "1",
                "-codec",
                "copy",
                str(path),
            ]
        )
        return path

    def make_faststart_transcode(self, input_path: Path, output_path: Path, vf="scale=854:480,fps=30"):
        self.run_cmd(
            [
                self.ffmpeg,
                "-y",
                "-i",
                str(input_path),
                "-map",
                "0",
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                vf,
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        return output_path

    def test_verify_output_rejects_truncated_output(self):
        with managed_tempdir("mnemo_test_truncate_") as base:
            inp = self.make_av_clip(base / "input60.mp4", duration=3.0, rate=60)
            outp = self.make_av_clip(base / "short_output.mp4", duration=1.5, size="854x480", rate=30)
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_verify_output_rejects_wrong_display_geometry(self):
        with managed_tempdir("mnemo_test_wrong_geometry_") as base:
            inp = self.make_av_clip(base / "input_aspect.mp4", duration=2.0, rate=30)
            outp = base / "wrong_aspect.mp4"
            self.run_cmd(
                [
                    self.ffmpeg,
                    "-y",
                    "-i",
                    str(inp),
                    "-map",
                    "0",
                    "-map_metadata",
                    "0",
                    "-map_chapters",
                    "0",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-vf",
                    "scale=100:480",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(outp),
                ]
            )
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_verify_output_rejects_stream_loss(self):
        with managed_tempdir("mnemo_test_stream_loss_") as base:
            inp = self.make_multistream_clip(base / "input_multi.mkv")
            outp = base / "output_single.mkv"
            self.run_cmd(
                [
                    self.ffmpeg,
                    "-y",
                    "-i",
                    str(inp),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-c:v",
                    "libx264",
                    "-vf",
                    "scale=854:480,fps=30",
                    "-c:a",
                    "aac",
                    str(outp),
                ]
            )
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_verify_output_rejects_non_yuv420_output(self):
        with managed_tempdir("mnemo_test_verify_pixfmt_") as base:
            inp = self.make_av_clip(base / "input_standard.mp4", duration=2.0, rate=60)
            outp = self.make_av_clip(
                base / "output_444.mp4",
                duration=2.0,
                size="854x480",
                rate=30,
                pix_fmt="yuv444p",
                video_bitrate="700k",
            )
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_verify_output_rejects_stream_descriptor_mismatch(self):
        with managed_tempdir("mnemo_test_stream_descriptor_") as base:
            inp = self.make_multistream_clip(base / "input_descriptor.mkv")
            outp = base / "output_descriptor.mkv"
            self.run_cmd(
                [
                    self.ffmpeg,
                    "-y",
                    "-i",
                    str(inp),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-map",
                    "0:a:1",
                    "-map",
                    "0:s:0",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-vf",
                    "scale=854:480,fps=30",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "96k",
                    "-ar:a:0",
                    "22050",
                    "-ar:a:1",
                    "44100",
                    "-c:s",
                    "copy",
                    "-metadata:s:a:0",
                    "language=eng",
                    "-metadata:s:a:1",
                    "language=tur",
                    "-metadata:s:s:0",
                    "language=tur",
                    "-disposition:a:0",
                    "default",
                    "-disposition:a:1",
                    "0",
                    "-disposition:s:0",
                    "default",
                    str(outp),
                ]
            )
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_verify_output_requires_full_decode_success(self):
        with managed_tempdir("mnemo_test_decode_gate_") as base:
            inp = self.make_av_clip(base / "input60.mp4", duration=2.0, rate=60, size="1280x720")
            outp = self.make_faststart_transcode(inp, base / "valid_output.mp4")
            # Disable frame counting so the decode-verification skip does not
            # trigger — when frame_check != "counted", verify_output must call
            # verify_media_decode and respect its result.
            with patch.object(mnemosyne, "verify_media_decode", return_value=False) as decode_mock:
                self.assertFalse(mnemosyne.verify_output(inp, outp, default_config(verify_frames=False)))
            decode_mock.assert_called_once()

    def test_verify_frames_false_skips_frame_counting_but_keeps_decode_gate(self):
        with managed_tempdir("mnemo_test_no_frame_count_") as base:
            inp = self.make_av_clip(base / "input60.mp4", duration=2.0, rate=60, size="1280x720")
            outp = self.make_faststart_transcode(inp, base / "valid_output.mp4")
            calls = []
            original_get_media_info = mnemosyne.get_media_info
            def spy_get_media_info(path, timeout=15, count_frames=False):
                calls.append(count_frames)
                return original_get_media_info(path, timeout=timeout, count_frames=count_frames)
            with patch.object(mnemosyne, "get_media_info", side_effect=spy_get_media_info), patch.object(
                mnemosyne, "verify_media_decode", return_value=True
            ):
                ok, details = mnemosyne.verify_output(inp, outp, default_config(verify_frames=False), return_details=True)
            self.assertTrue(ok)
            self.assertEqual(details["frame_check"], "disabled")
            self.assertTrue(details["decode_ok"])
            self.assertTrue(calls)
            self.assertFalse(any(calls))

    def test_verify_media_decode_rejects_faststart_truncation(self):
        with managed_tempdir("mnemo_test_decode_truncation_") as base:
            inp = self.make_av_clip(base / "input60.mp4", duration=2.5, rate=60)
            outp = self.make_faststart_transcode(inp, base / "faststart_output.mp4")
            original = outp.read_bytes()
            # With faststart the moov atom is at the front, so truncating the tail
            # may still leave enough mdat data to decode. Instead, corrupt bytes
            # in the mdat portion — metadata (moov) will read fine but decode will
            # produce errors.
            mdat_start = original.find(b'mdat')
            if mdat_start < 0:
                self.skipTest("Could not locate mdat in faststart output")
            # Corrupt 2 KB of mdat payload data (skip the 8-byte mdat header).
            corrupted = bytearray(original)
            corrupt_offset = mdat_start + 8
            for i in range(min(2048, len(corrupted) - corrupt_offset)):
                corrupted[corrupt_offset + i] ^= 0xFF
            outp.write_bytes(bytes(corrupted))
            info = mnemosyne.get_media_info(outp)
            # Metadata should still be readable since moov is at the front.
            self.assertGreater(info.get("duration", 0.0), 0.0)
            self.assertFalse(mnemosyne.verify_media_decode(outp, info))

    def test_get_media_info_counts_frames_when_requested_for_mkv(self):
        with managed_tempdir("mnemo_test_count_frames_") as base:
            source = self.make_multistream_clip(base / "counted.mkv")
            default_info = mnemosyne.get_media_info(source)
            counted_info = mnemosyne.get_media_info(source, count_frames=True)
            self.assertEqual(default_info["frame_count"], -1)
            self.assertGreater(counted_info["frame_count"], 0)

    def test_verify_output_rejects_chapter_title_mismatch(self):
        with managed_tempdir("mnemo_test_chapter_titles_") as base:
            inp = self.make_chaptered_clip(base / "input_chapters.mkv")
            outp = base / "output_chapters.mkv"
            metadata_path = base / "chapters_changed.ffmeta"
            metadata_path.write_text(
                ";FFMETADATA1\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=900\ntitle=Intro Renamed\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=900\nEND=1800\ntitle=Main\n",
                encoding="utf-8",
            )
            self.run_cmd(
                [
                    self.ffmpeg,
                    "-y",
                    "-i",
                    str(inp),
                    "-f",
                    "ffmetadata",
                    "-i",
                    str(metadata_path),
                    "-map",
                    "0",
                    "-map_metadata",
                    "0",
                    "-map_chapters",
                    "1",
                    "-codec",
                    "copy",
                    str(outp),
                ]
            )
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_verify_output_rejects_stream_title_mismatch(self):
        with managed_tempdir("mnemo_test_stream_titles_") as base:
            inp = self.make_multistream_clip(base / "input_titles.mkv")
            outp = base / "output_titles.mkv"
            self.run_cmd(
                [
                    self.ffmpeg,
                    "-y",
                    "-i",
                    str(inp),
                    "-map",
                    "0",
                    "-map_metadata",
                    "0",
                    "-map_chapters",
                    "0",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-vf",
                    "scale=854:480,fps=30",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-c:s",
                    "copy",
                    "-metadata:s:a:0",
                    "language=eng",
                    "-metadata:s:a:1",
                    "language=tur",
                    "-metadata:s:s:0",
                    "language=eng",
                    "-metadata:s:a:0",
                    "title=Renamed Main",
                    "-metadata:s:a:1",
                    "title=Turkish Alt",
                    "-metadata:s:s:0",
                    "title=English Subtitle",
                    "-disposition:a:0",
                    "default",
                    "-disposition:a:1",
                    "0",
                    "-disposition:s:0",
                    "default",
                    str(outp),
                ]
            )
            self.assertFalse(mnemosyne.verify_output(inp, outp, default_config()))

    def test_compare_copy_streams_rejects_attachment_mimetype_mismatch(self):
        in_info = {
            "attachment_streams": [
                {"codec": "ttf", "language": "und", "default": 0, "forced": 0, "title": "", "filename": "font.ttf", "mimetype": "application/x-truetype-font"}
            ]
        }
        out_info = {
            "attachment_streams": [
                {"codec": "ttf", "language": "und", "default": 0, "forced": 0, "title": "", "filename": "font.ttf", "mimetype": "application/octet-stream"}
            ]
        }
        self.assertFalse(mnemosyne.compare_copy_streams(in_info, out_info, "attachment_streams"))

    def test_should_skip_video_rejects_multi_video_inputs(self):
        with managed_tempdir("mnemo_test_skip_multivideo_") as base:
            source = self.make_multi_video_clip(base / "multi_video.mp4")
            self.assertFalse(mnemosyne.should_skip_video(source, default_config()))

    def test_should_skip_video_requires_yuv420p(self):
        with managed_tempdir("mnemo_test_skip_pixfmt_") as base:
            source = self.make_av_clip(
                base / "already_small_444.mp4",
                duration=2.0,
                size="640x360",
                rate=30,
                pix_fmt="yuv444p",
                video_bitrate="600k",
            )
            self.assertFalse(mnemosyne.should_skip_video(source, default_config()))

    def test_process_video_preserves_low_fps_sources(self):
        with managed_tempdir("mnemo_test_lowfps_") as base:
            source = self.make_av_clip(base / "input24.mp4", duration=2.0, rate=24)
            result = mnemosyne.process_video(1, source, "libx264", default_config())
            info = mnemosyne.get_media_info(source)
            self.assertEqual(result, 1)
            self.assertAlmostEqual(info["fps"], 24.0, delta=0.5)
            self.assertEqual(info["height"], 480)
            self.assertEqual(info["frame_count"], 48)

    def test_process_video_downsamples_high_fps_sources(self):
        with managed_tempdir("mnemo_test_highfps_") as base:
            source = self.make_av_clip(base / "input60.mp4", duration=2.0, rate=60)
            result = mnemosyne.process_video(1, source, "libx264", default_config())
            info = mnemosyne.get_media_info(source)
            self.assertEqual(result, 1)
            self.assertAlmostEqual(info["fps"], 30.0, delta=0.5)
            self.assertEqual(info["height"], 480)

    def test_process_video_converts_yuv444p_to_yuv420p(self):
        with managed_tempdir("mnemo_test_pixfmt_convert_") as base:
            source = self.make_av_clip(
                base / "input444.mp4",
                duration=2.0,
                size="640x360",
                rate=60,
                pix_fmt="yuv444p",
                video_bitrate="1600k",
            )
            result = mnemosyne.process_video(1, source, "libx264", default_config())
            info = mnemosyne.get_media_info(source)
            self.assertEqual(result, 1)
            self.assertAlmostEqual(info["fps"], 30.0, delta=0.5)
            self.assertEqual(info["video_pix_fmt"], "yuv420p")

    def test_process_video_preserves_chapters(self):
        with managed_tempdir("mnemo_test_chapters_") as base:
            source = self.make_chaptered_clip(base / "chaptered.mkv")
            result = mnemosyne.process_video(1, source, "libx264", default_config())
            info = mnemosyne.get_media_info(source)
            self.assertEqual(result, 1)
            self.assertEqual(info["chapter_count"], 2)
            self.assertEqual(info["audio_stream_count"], 1)

    def test_process_video_preserves_mtime_when_enabled(self):
        with managed_tempdir("mnemo_test_meta_on_") as base:
            source = self.make_av_clip(base / "meta_on.mp4", duration=1.5, rate=60)
            old_ts = 946684800
            os.utime(source, (old_ts, old_ts))
            result = mnemosyne.process_video(1, source, "libx264", default_config(preserve_metadata=True))
            self.assertEqual(result, 1)
            self.assertAlmostEqual(source.stat().st_mtime, old_ts, delta=2.0)

    def test_process_video_changes_mtime_when_metadata_disabled(self):
        with managed_tempdir("mnemo_test_meta_off_") as base:
            source = self.make_av_clip(base / "meta_off.mp4", duration=1.5, rate=60)
            old_ts = 946684800
            os.utime(source, (old_ts, old_ts))
            result = mnemosyne.process_video(1, source, "libx264", default_config(preserve_metadata=False))
            self.assertEqual(result, 1)
            self.assertGreater(abs(source.stat().st_mtime - old_ts), 2.0)

    def test_cleanup_temp_files_only_removes_managed_workspace(self):
        with managed_tempdir("mnemo_test_cleanup_") as base:
            plain_file = base / "mnemosyne_tmp_family_video.mp4"
            plain_file.write_bytes(b"keep me")
            managed_workspace = make_stale_workspace(base)
            managed_file = managed_workspace / "artifact.mp4"
            managed_file.write_bytes(b"delete me")
            deleted_count = mnemosyne.cleanup_temp_files(base, recursive=False)
            self.assertEqual(deleted_count, 1)
            self.assertTrue(plain_file.exists())
            self.assertFalse(managed_file.exists())
            self.assertFalse(managed_workspace.exists())

    def test_cleanup_temp_files_preserves_active_workspace_until_current_session_cleanup(self):
        with managed_tempdir("mnemo_test_cleanup_active_") as base:
            active_workspace = mnemosyne.get_temp_workspace(base)
            managed_file = active_workspace / "artifact.mp4"
            managed_file.write_bytes(b"keep while active")
            deleted_count = mnemosyne.cleanup_temp_files(base, recursive=False)
            self.assertEqual(deleted_count, 0)
            self.assertTrue(managed_file.exists())
            deleted_count = mnemosyne.cleanup_temp_files(base, recursive=False, include_current_session=True)
            self.assertEqual(deleted_count, 1)
            self.assertFalse(active_workspace.exists())

    def test_get_temp_workspace_is_thread_safe_for_current_session(self):
        with managed_tempdir("mnemo_test_workspace_race_") as base:
            start = threading.Event()
            results = []

            def worker(index: int):
                start.wait()
                try:
                    workspace = mnemosyne.get_temp_workspace(base)
                    results.append((index, "ok", str(workspace.resolve())))
                except Exception as exc:
                    results.append((index, "err", str(exc)))

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(12)]
            for thread in threads:
                thread.start()
            start.set()
            for thread in threads:
                thread.join()

            errors = [message for _index, status, message in results if status == "err"]
            self.assertFalse(errors, errors)
            workspaces = {message for _index, status, message in results if status == "ok"}
            self.assertEqual(len(workspaces), 1)

    def test_audit_orphaned_backups_restore_without_current_file(self):
        with managed_tempdir("mnemo_test_restore_") as base:
            original = base / "movie.mp4"
            backup = base / "movie.mp4.bak"
            backup.write_bytes(b"old")
            with pushd(base), patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch("builtins.input", side_effect=["r"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            self.assertTrue(result)
            self.assertTrue(original.exists())
            self.assertFalse(backup.exists())
            self.assertEqual(original.read_bytes(), b"old")

    def test_audit_orphaned_backups_restore_requires_empty_target(self):
        with managed_tempdir("mnemo_test_restore_conflict_") as base:
            original = base / "movie.mp4"
            backup = base / "movie.mp4.bak"
            original.write_bytes(b"new")
            backup.write_bytes(b"old")
            with pushd(base), patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch("builtins.input", side_effect=["r"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            self.assertFalse(result)
            self.assertTrue(original.exists())
            self.assertTrue(backup.exists())
            self.assertEqual(original.read_bytes(), b"new")
            self.assertEqual(backup.read_bytes(), b"old")

    def test_audit_orphaned_backups_preserves_current_before_restore(self):
        with managed_tempdir("mnemo_test_restore_preserve_current_") as base:
            original = base / "movie.mp4"
            backup = base / "movie.mp4.bak"
            original.write_bytes(b"new")
            backup.write_bytes(b"old")
            with pushd(base), patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch("builtins.input", side_effect=["k"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            preserved = list(base.glob("movie.rescued-current-*.mp4"))
            self.assertTrue(result)
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0].read_bytes(), b"new")
            self.assertEqual(original.read_bytes(), b"old")
            self.assertFalse(backup.exists())

    def test_audit_orphaned_backups_overwrites_current_with_safe_hold(self):
        with managed_tempdir("mnemo_test_restore_overwrite_current_") as base:
            original = base / "movie.mp4"
            backup = base / "movie.mp4.bak"
            original.write_bytes(b"new")
            backup.write_bytes(b"old")
            with pushd(base), patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch("builtins.input", side_effect=["o"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            self.assertTrue(result)
            self.assertEqual(original.read_bytes(), b"old")
            self.assertFalse(backup.exists())
            self.assertEqual(list(base.glob("movie.overwrite-hold-*.mp4")), [])

    def test_audit_orphaned_backups_purge_requires_explicit_confirmation(self):
        with managed_tempdir("mnemo_test_purge_guard_") as base:
            backup = base / "movie.mp4.bak"
            backup.write_bytes(b"old")
            with pushd(base), patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch("builtins.input", side_effect=["p", "NOPE"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            self.assertFalse(result)
            self.assertTrue(backup.exists())
            self.assertIn("Cancelled", output.getvalue())

    def test_audit_orphaned_backups_does_not_cleanup_when_disabled(self):
        with managed_tempdir("mnemo_test_no_cleanup_") as base:
            managed_workspace = mnemosyne.get_temp_workspace(base)
            managed_file = managed_workspace / "artifact.mp4"
            managed_file.write_bytes(b"keep while cleanup disabled")
            with pushd(base):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=False)
            self.assertTrue(result)
            self.assertTrue(managed_file.exists())
            self.assertIn("Auto-cleanup is disabled", output.getvalue())

    def test_audit_orphaned_backups_noninteractive_requires_manual_resolution(self):
        with managed_tempdir("mnemo_test_headless_bak_") as base:
            backup = base / "movie.mp4.bak"
            backup.write_bytes(b"old")
            with pushd(base), patch.object(mnemosyne, "supports_interactive_input", return_value=False), patch(
                "builtins.input", side_effect=AssertionError("input should not be called")
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            self.assertFalse(result)
            self.assertTrue(backup.exists())
            self.assertIn("Non-interactive mode cannot decide", output.getvalue())

    def test_audit_orphaned_backups_surfaces_transaction_journal_state(self):
        with managed_tempdir("mnemo_test_journal_rescue_") as base:
            backup = base / "movie.mp4.bak"
            backup.write_bytes(b"old")
            journal_path = mnemosyne.get_transaction_journal_path(backup)
            journal_path.write_text(
                json.dumps(
                    {
                        "stage": "backup_cleanup_failed",
                        "verification": {"metadata_ok": True, "decode_ok": True, "frame_check": "counted"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with pushd(base), patch("builtins.input", side_effect=["s"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = mnemosyne.audit_orphaned_backups(recursive=False, auto_cleanup=True)
            self.assertFalse(result)
            self.assertIn("backup_cleanup_failed", output.getvalue())

    def test_iter_video_files_filters_special_dirs_and_supports_uppercase_extensions(self):
        with managed_tempdir("mnemo_test_discovery_") as base:
            expected = {
                str((base / "ROOT.MP4").resolve()),
                str((base / "nested" / "clip.MKV").resolve()),
                str((base / "bin" / "skip.mp4").resolve()),
                str((base / "logs" / "skip.mkv").resolve()),
            }
            (base / "nested").mkdir()
            (base / "bin").mkdir()
            (base / "logs").mkdir()
            (base / "ROOT.MP4").write_bytes(b"x")
            (base / "nested" / "clip.MKV").write_bytes(b"x")
            (base / "bin" / "skip.mp4").write_bytes(b"x")
            (base / "logs" / "skip.mkv").write_bytes(b"x")
            temp_workspace = mnemosyne.get_temp_workspace(base)
            (temp_workspace / "ignore.mp4").write_bytes(b"x")
            discovered = {str(path.resolve()) for path in mnemosyne.iter_video_files(base, recursive=True)}
            self.assertSetEqual(discovered, expected)

    def test_install_binaries_atomically_preserves_existing_install_on_incomplete_stage(self):
        with managed_tempdir("mnemo_test_atomic_install_") as base:
            live_bin = base / "live_bin"
            live_bin.mkdir()
            old_ffmpeg = live_bin / ("ffmpeg.exe" if mnemosyne.IS_WINDOWS else "ffmpeg")
            old_ffprobe = live_bin / ("ffprobe.exe" if mnemosyne.IS_WINDOWS else "ffprobe")
            old_ffmpeg.write_bytes(b"old_ffmpeg")
            old_ffprobe.write_bytes(b"old_ffprobe")
            stage_dir = base / "stage_bin"
            stage_dir.mkdir()
            old_ffmpeg_stage = stage_dir / old_ffmpeg.name
            old_ffmpeg_stage.write_bytes(b"new_ffmpeg")
            with patch.object(mnemosyne, "BIN_DIR", live_bin):
                with self.assertRaises(RuntimeError):
                    mnemosyne.install_binaries_atomically(stage_dir, [old_ffmpeg.name, old_ffprobe.name])
            self.assertEqual(old_ffmpeg.read_bytes(), b"old_ffmpeg")
            self.assertEqual(old_ffprobe.read_bytes(), b"old_ffprobe")

    def test_process_video_refuses_stale_backup(self):
        with managed_tempdir("mnemo_test_stale_bak_") as base:
            source = self.make_av_clip(base / "stale.mp4", duration=1.5, rate=60)
            backup = source.with_suffix(source.suffix + ".bak")
            backup.write_bytes(b"existing backup")
            original_bytes = source.read_bytes()
            with self.assertLogs(level="ERROR") as logs:
                result = mnemosyne.process_video(1, source, "libx264", default_config())
            self.assertFalse(result)
            self.assertTrue(backup.exists())
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertIn("Stale backup already exists", "\n".join(logs.output))

    def test_process_video_rejects_multi_video_inputs_without_touching_original(self):
        with managed_tempdir("mnemo_test_multi_video_reject_") as base:
            source = self.make_multi_video_clip(base / "multi_video.mp4")
            original_bytes = source.read_bytes()
            backup = source.with_suffix(source.suffix + ".bak")
            with self.assertLogs(level="ERROR") as logs:
                result = mnemosyne.process_video(1, source, "libx264", default_config())
            self.assertFalse(result)
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertFalse(backup.exists())
            self.assertIn("Unsupported multi-video-stream input", "\n".join(logs.output))

    def test_test_encoder_uses_gpu_safe_probe_dimensions(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("mnemosyne.subprocess.run", return_value=completed) as run_mock:
            self.assertTrue(mnemosyne._test_encoder("h264_nvenc"))
        cmd = run_mock.call_args.args[0]
        self.assertIn("nullsrc=s=256x256:r=30", cmd)
        self.assertEqual(cmd[cmd.index("-pix_fmt") + 1], "yuv420p")

    def test_render_progress_falls_back_to_ascii_when_unicode_output_is_unavailable(self):
        with patch.object(mnemosyne, "supports_unicode_output", return_value=False):
            rendered = mnemosyne.render_progress("clip.mp4", 50.0, "30", "1.0x", "10MB -> 5MB")
        self.assertIn(">", rendered)
        self.assertIn("#", rendered)
        self.assertIn("|-", rendered)
        for glyph in ("█", "░", "✓", "➤", "└"):
            self.assertNotIn(glyph, rendered)

    def test_draw_header_respects_narrow_width(self):
        width = 44
        header = mnemosyne.draw_header(
            default_config(max_workers=8),
            "NVIDIA (NVENC) with an unusually long display name",
            width=width,
        )
        for line in header.splitlines():
            self.assertLessEqual(len(mnemosyne.strip_ansi(line)), width + 5)

    def test_update_display_uses_compact_mode_on_small_terminals(self):
        fake_stdout = FakeStdout(isatty_result=True)
        stats = mnemosyne.WorkerStats()
        stats.update(
            1,
            "Desktop Capture With Very Long Filename 2026.03.26.mp4",
            42.5,
            "30",
            "1.2x",
            "100MB -> 40MB",
        )
        prior_state = mnemosyne.DISPLAY_STATE.copy()
        try:
            mnemosyne.DISPLAY_STATE.update({"mode": None, "last_compact_at": 0.0, "last_compact_snapshot": ""})
            with patch.object(mnemosyne, "worker_stats", stats):
                with patch.object(mnemosyne.sys, "stdout", fake_stdout):
                    with patch("mnemosyne.shutil.get_terminal_size", return_value=os.terminal_size((60, 12))):
                        mnemosyne.update_display(5, 1, "CPU (x264)", default_config())
        finally:
            mnemosyne.DISPLAY_STATE.update(prior_state)
        rendered = fake_stdout.getvalue()
        self.assertIn("[Progress]", rendered)
        self.assertNotIn("\033[H", rendered)

    def test_show_security_notice_skips_pause_when_noninteractive(self):
        with patch.object(mnemosyne, "supports_interactive_input", return_value=False), patch.object(
            mnemosyne, "clear_screen"
        ), patch.object(mnemosyne, "draw_separator"), patch.object(mnemosyne, "draw_box_line"), patch(
            "builtins.input", side_effect=AssertionError("input should not be called")
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                mnemosyne.show_security_notice("C:/tmp/Mnemosyne_Log.txt")

    def test_safe_input_returns_default_on_eof(self):
        with patch("builtins.input", side_effect=EOFError):
            self.assertEqual(mnemosyne.safe_input("prompt", "fallback"), "fallback")

    def test_prompt_menu_choice_returns_default_on_eof(self):
        with patch("builtins.input", side_effect=EOFError):
            self.assertEqual(mnemosyne.prompt_menu_choice("Mode", "2", {"1", "2"}), "2")

    def test_edit_session_settings_profile_menu_changes_profile(self):
        context = mnemosyne.RunContext(
            mode="folder-scan",
            session_config=default_config(),
            ffmpeg_preferences={"auto_download": False, "storage_mode": "session", "custom_install_path": ""},
        )
        with patch.object(mnemosyne, "clear_screen"), patch.object(mnemosyne, "draw_header", return_value="header"), patch(
            "builtins.input", side_effect=["1", "3", "b"]
        ), contextlib.redirect_stdout(io.StringIO()):
            mnemosyne.edit_session_settings(context, mnemosyne.default_ffmpeg_state())
        self.assertEqual(context.session_config["profile_id"], "720p")
        self.assertEqual(context.session_config["target_height"], 720)
        self.assertEqual(context.session_config["video_bitrate"], "1800k")
        self.assertEqual(context.session_config["audio_bitrate"], "160k")
        self.assertEqual(context.session_config["target_fps"], 30)

    def test_edit_session_settings_handles_eof(self):
        context = mnemosyne.RunContext(
            mode="folder-scan",
            session_config=default_config(),
            ffmpeg_preferences={"auto_download": False, "storage_mode": "session", "custom_install_path": ""},
        )
        with patch.object(mnemosyne, "clear_screen"), patch.object(mnemosyne, "draw_header", return_value="header"), patch(
            "builtins.input", side_effect=EOFError
        ), contextlib.redirect_stdout(io.StringIO()):
            mnemosyne.edit_session_settings(context, mnemosyne.default_ffmpeg_state())

    def test_ensure_ffmpeg_noninteractive_declines_download_without_prompt(self):
        with patch.object(mnemosyne, "check_ffmpeg_with_policy", return_value=False), patch.object(
            mnemosyne, "supports_interactive_input", return_value=False
        ), patch.object(mnemosyne, "download_ffmpeg") as download_mock, patch(
            "builtins.input", side_effect=AssertionError("input should not be called")
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertFalse(mnemosyne.ensure_ffmpeg(auto_download=False))
        download_mock.assert_not_called()
        self.assertIn("FFmpeg could not be downloaded or found", output.getvalue())

    def test_main_noninteractive_starts_without_ready_prompt_when_config_exists(self):
        with managed_tempdir("mnemo_test_headless_main_") as base:
            source = base / "queued.mp4"
            source.write_bytes(b"x")
            config = default_config()
            argv_backup = sys.argv[:]
            try:
                with pushd(base), contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(mnemosyne, "supports_interactive_input", return_value=False))
                    stack.enter_context(patch.object(mnemosyne, "show_security_notice"))
                    stack.enter_context(patch.object(mnemosyne, "ensure_ffmpeg", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "detect_gpu_codec", return_value=("libx264", "CPU (x264)")))
                    stack.enter_context(patch.object(mnemosyne, "has_saved_config", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "load_config", return_value=config.copy()))
                    stack.enter_context(patch.object(mnemosyne, "iter_video_files", return_value=iter([source])))
                    stack.enter_context(patch.object(mnemosyne, "should_skip_video", return_value=False))
                    process_mock = stack.enter_context(patch.object(mnemosyne, "process_video", return_value=2))
                    stack.enter_context(patch.object(mnemosyne, "setup_logging", return_value=base / "Mnemosyne_Log.txt"))
                    stack.enter_context(patch.object(mnemosyne, "audit_orphaned_backups", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "clear_screen"))
                    stack.enter_context(patch.object(mnemosyne, "hide_cursor"))
                    stack.enter_context(patch.object(mnemosyne, "show_cursor"))
                    stack.enter_context(patch.object(mnemosyne, "update_display"))
                    stack.enter_context(patch.object(mnemosyne, "draw_header", return_value="header"))
                    stack.enter_context(patch.object(mnemosyne, "draw_logo", return_value="logo"))
                    stack.enter_context(patch.object(mnemosyne, "draw_separator"))
                    stack.enter_context(patch.object(mnemosyne, "draw_box_line"))
                    stack.enter_context(patch("builtins.input", side_effect=AssertionError("input should not be called")))
                    sys.argv = ["mnemosyne.py"]
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = mnemosyne.main()
            finally:
                sys.argv = argv_backup
            self.assertEqual(result, 0)
            process_mock.assert_called_once()

    def test_main_stops_when_orphaned_backups_are_unresolved(self):
        with managed_tempdir("mnemo_test_headless_rescue_stop_") as base:
            config = default_config()
            argv_backup = sys.argv[:]
            try:
                with pushd(base), contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(mnemosyne, "supports_interactive_input", return_value=False))
                    stack.enter_context(patch.object(mnemosyne, "show_security_notice"))
                    stack.enter_context(patch.object(mnemosyne, "ensure_ffmpeg", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "detect_gpu_codec", return_value=("libx264", "CPU (x264)")))
                    stack.enter_context(patch.object(mnemosyne, "has_saved_config", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "load_config", return_value=config.copy()))
                    process_mock = stack.enter_context(patch.object(mnemosyne, "process_video", return_value=1))
                    stack.enter_context(patch.object(mnemosyne, "setup_logging", return_value=base / "Mnemosyne_Log.txt"))
                    stack.enter_context(patch.object(mnemosyne, "audit_orphaned_backups", return_value=False))
                    stack.enter_context(patch.object(mnemosyne, "clear_screen"))
                    stack.enter_context(patch.object(mnemosyne, "draw_logo", return_value="logo"))
                    stack.enter_context(patch("builtins.input", side_effect=AssertionError("input should not be called")))
                    sys.argv = ["mnemosyne.py"]
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = mnemosyne.main()
            finally:
                sys.argv = argv_backup
            self.assertEqual(result, 1)
            process_mock.assert_not_called()

    def test_save_config_writes_global_only(self):
        with managed_tempdir("mnemo_test_global_save_") as base:
            app_dir = base / "appdata"
            app_config = app_dir / "config.json"
            local_config = base / "config.json"
            with pushd(base), patch.object(mnemosyne, "APP_DATA", app_dir), patch.object(
                mnemosyne, "APP_CONFIG_FILE", app_config
            ):
                self.assertTrue(mnemosyne.save_config(default_config()))
            self.assertTrue(app_config.exists())
            self.assertFalse(local_config.exists())

    def test_main_stateless_start_does_not_create_saved_config(self):
        with managed_tempdir("mnemo_test_no_autosave_") as base:
            app_dir = base / "appdata"
            app_config = app_dir / "config.json"
            argv_backup = sys.argv[:]
            try:
                with pushd(base), contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(mnemosyne, "APP_DATA", app_dir))
                    stack.enter_context(patch.object(mnemosyne, "APP_CONFIG_FILE", app_config))
                    stack.enter_context(patch.object(mnemosyne, "supports_interactive_input", return_value=False))
                    stack.enter_context(patch.object(mnemosyne, "show_security_notice"))
                    stack.enter_context(patch.object(mnemosyne, "prompt_stale_ffmpeg_cleanup"))
                    stack.enter_context(patch.object(mnemosyne, "setup_logging", return_value=base / "Mnemosyne_Log.txt"))
                    stack.enter_context(patch.object(mnemosyne, "audit_orphaned_backups", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "iter_video_files", return_value=iter([])))
                    stack.enter_context(patch.object(mnemosyne, "clear_screen"))
                    stack.enter_context(patch.object(mnemosyne, "draw_logo", return_value="logo"))
                    stack.enter_context(patch("builtins.input", side_effect=AssertionError("input should not be called")))
                    sys.argv = ["mnemosyne.py"]
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = mnemosyne.main()
            finally:
                sys.argv = argv_backup
            self.assertEqual(result, 1)
            self.assertFalse(app_config.exists())

    def test_explicit_file_mode_processes_only_dropped_files_in_order(self):
        with managed_tempdir("mnemo_test_explicit_inputs_") as base:
            dropped_b = base / "drop_b.mp4"
            dropped_a = base / "drop_a.mp4"
            extra = base / "extra.mp4"
            ignored_dir = base / "folder"
            ignored_dir.mkdir()
            ignored_text = base / "notes.txt"
            for path in (dropped_b, dropped_a, extra):
                path.write_bytes(b"x")
            ignored_text.write_text("ignore me", encoding="utf-8")
            config = default_config(max_workers=1)
            argv_backup = sys.argv[:]
            try:
                with pushd(base), contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(mnemosyne, "supports_interactive_input", return_value=False))
                    stack.enter_context(patch.object(mnemosyne, "show_security_notice"))
                    stack.enter_context(patch.object(mnemosyne, "prompt_stale_ffmpeg_cleanup"))
                    stack.enter_context(patch.object(mnemosyne, "ensure_ffmpeg", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "detect_gpu_codec", return_value=("libx264", "CPU (x264)")))
                    stack.enter_context(patch.object(mnemosyne, "load_config", return_value=config.copy()))
                    stack.enter_context(patch.object(mnemosyne, "setup_logging", return_value=base / "Mnemosyne_Log.txt"))
                    stack.enter_context(patch.object(mnemosyne, "audit_orphaned_backups", return_value=True))
                    stack.enter_context(patch.object(mnemosyne, "iter_video_files", side_effect=AssertionError("explicit mode should not scan folders")))
                    stack.enter_context(patch.object(mnemosyne, "should_skip_video", return_value=False))
                    process_mock = stack.enter_context(patch.object(mnemosyne, "process_video", return_value=2))
                    stack.enter_context(patch.object(mnemosyne, "clear_screen"))
                    stack.enter_context(patch.object(mnemosyne, "hide_cursor"))
                    stack.enter_context(patch.object(mnemosyne, "show_cursor"))
                    stack.enter_context(patch.object(mnemosyne, "update_display"))
                    stack.enter_context(patch.object(mnemosyne, "draw_header", return_value="header"))
                    stack.enter_context(patch.object(mnemosyne, "draw_logo", return_value="logo"))
                    stack.enter_context(patch.object(mnemosyne, "draw_separator"))
                    stack.enter_context(patch.object(mnemosyne, "draw_box_line"))
                    stack.enter_context(patch("builtins.input", side_effect=AssertionError("input should not be called")))
                    sys.argv = [
                        "mnemosyne.py",
                        "--workers",
                        "1",
                        str(dropped_b),
                        str(ignored_dir),
                        str(ignored_text),
                        str(dropped_a),
                    ]
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = mnemosyne.main()
            finally:
                sys.argv = argv_backup
            self.assertEqual(result, 0)
            self.assertEqual([call.args[1] for call in process_mock.call_args_list], [dropped_b.resolve(), dropped_a.resolve()])
            self.assertNotIn(extra.resolve(), [call.args[1] for call in process_mock.call_args_list])

    def test_folder_path_argument_scans_that_folder(self):
        with managed_tempdir("mnemo_test_folder_arg_") as base:
            target = base / "target"
            other = base / "other"
            target.mkdir()
            other.mkdir()
            wanted = target / "wanted.mp4"
            ignored = other / "ignored.mp4"
            wanted.write_bytes(b"x")
            ignored.write_bytes(b"x")
            args = argparse.Namespace(paths=[str(target)], recursive=False, workers=None, height=None, desktop_log=False, codec="auto")
            context = mnemosyne.build_run_context(args, argparse.ArgumentParser())
            self.assertEqual(context.mode, "folder-scan")
            self.assertEqual(context.target_dirs, [target.resolve()])
            with patch.object(mnemosyne, "should_skip_video", return_value=False):
                videos, total_in, skipped_pre = mnemosyne.scan_videos_for_context(context)
            self.assertEqual(videos, [wanted.resolve()])
            self.assertEqual(total_in, 1)
            self.assertEqual(skipped_pre, 0)

    def test_mixed_file_and_folder_keeps_explicit_file_mode(self):
        with managed_tempdir("mnemo_test_mixed_arg_") as base:
            dropped = base / "dropped.mp4"
            folder = base / "folder"
            dropped.write_bytes(b"x")
            folder.mkdir()
            args = argparse.Namespace(paths=[str(dropped), str(folder)], recursive=False, workers=None, height=None, desktop_log=False, codec="auto")
            context = mnemosyne.build_run_context(args, argparse.ArgumentParser())
            self.assertEqual(context.mode, "explicit-files")
            self.assertEqual(context.input_files, [dropped.resolve()])
            self.assertIn(folder.resolve(), context.invalid_inputs)

    def test_cleanup_temp_files_targets_only_requested_dirs(self):
        with managed_tempdir("mnemo_test_targeted_cleanup_") as base:
            target_a = base / "target_a"
            target_b = base / "target_b"
            untouched = base / "untouched"
            for folder in (target_a, target_b, untouched):
                workspace = make_stale_workspace(folder)
                (workspace / "temp.bin").write_bytes(b"x")
            cleaned = mnemosyne.cleanup_temp_files(target_dirs=[target_a, target_b], recursive=False)
            self.assertEqual(cleaned, 2)
            self.assertFalse((target_a / mnemosyne.TEMP_WORKSPACE_NAME).exists())
            self.assertFalse((target_b / mnemosyne.TEMP_WORKSPACE_NAME).exists())
            self.assertTrue((untouched / mnemosyne.TEMP_WORKSPACE_NAME).exists())

    def test_audit_orphaned_backups_limits_scope_to_target_dirs(self):
        with managed_tempdir("mnemo_test_targeted_rescue_") as base:
            target_a = base / "target_a"
            target_b = base / "target_b"
            ignored = base / "ignored"
            for folder, name in ((target_a, "a.mp4.bak"), (target_b, "b.mp4.bak"), (ignored, "c.mp4.bak")):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_bytes(b"x")
            output = io.StringIO()
            with patch.object(mnemosyne, "supports_interactive_input", return_value=False), contextlib.redirect_stdout(output):
                self.assertFalse(
                    mnemosyne.audit_orphaned_backups(target_dirs=[target_a, target_b], recursive=False, auto_cleanup=False)
                )
            rendered = output.getvalue()
            self.assertIn("a.mp4.bak", rendered)
            self.assertIn("b.mp4.bak", rendered)
            self.assertNotIn("c.mp4.bak", rendered)

    def test_build_run_context_marks_removable_targets_per_file(self):
        with managed_tempdir("mnemo_test_removable_targets_") as base:
            removable_file = base / "usb.mp4"
            fixed_file = base / "ssd.mp4"
            removable_file.write_bytes(b"x")
            fixed_file.write_bytes(b"x")
            args = argparse.Namespace(
                paths=[str(removable_file), str(fixed_file)],
                recursive=False,
                workers=None,
                height=None,
                desktop_log=False,
                codec="auto",
            )
            parser = argparse.ArgumentParser()
            with patch.object(mnemosyne, "get_drive_type", side_effect=lambda path: 2 if str(removable_file) == path else 3):
                context = mnemosyne.build_run_context(args, parser)
            self.assertEqual(context.removable_targets, [removable_file.resolve()])
            self.assertEqual(context.session_config["max_workers"], 1)

    def test_handle_interrupt_uses_runtime_state_scope(self):
        old_state = mnemosyne.RUNTIME_STATE.copy()
        try:
            target = Path("/tmp/mnemosyne-target")
            mnemosyne.RUNTIME_STATE.update({"recursive": True, "auto_cleanup": True, "target_dirs": [target]})
            with patch.object(mnemosyne.PROCESS_MGR, "kill_all") as kill_mock, patch.object(mnemosyne, "show_cursor"), patch.object(
                mnemosyne, "cleanup_temp_files"
            ) as cleanup_mock, patch.object(mnemosyne, "iter_video_backups", return_value=[]), patch.object(
                mnemosyne.os, "_exit", side_effect=SystemExit(130)
            ) as exit_mock, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    mnemosyne.handle_interrupt()
            kill_mock.assert_called_once()
            cleanup_mock.assert_called_once_with(recursive=True, include_current_session=True, target_dirs=[target])
            exit_mock.assert_called_once_with(130)
        finally:
            mnemosyne.RUNTIME_STATE.clear()
            mnemosyne.RUNTIME_STATE.update(old_state)

    def test_prompt_stale_ffmpeg_cleanup_removes_old_managed_install(self):
        with managed_tempdir("mnemo_test_stale_ffmpeg_") as base:
            app_dir = base / "appdata"
            state_file = app_dir / "ffmpeg_state.json"
            install_dir = base / "portable_bin"
            install_dir.mkdir(parents=True, exist_ok=True)
            for binary_name in ("ffmpeg.exe", "ffprobe.exe") if mnemosyne.IS_WINDOWS else ("ffmpeg", "ffprobe"):
                (install_dir / binary_name).write_text("binary", encoding="utf-8")
            state = {
                "preferred_storage_mode": "portable",
                "preferred_custom_path": "",
                "managed_installs": [
                    {
                        "install_path": str(install_dir.resolve()),
                        "storage_mode": "portable",
                        "source_identity": "test-source",
                        "created_at": int(time.time()) - (10 * 86400),
                        "last_used_at": int(time.time()) - (10 * 86400),
                    }
                ],
            }
            with patch.object(mnemosyne, "APP_DATA", app_dir), patch.object(mnemosyne, "FFMPEG_STATE_FILE", state_file):
                self.assertTrue(mnemosyne.save_ffmpeg_state(state))
                with patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch("builtins.input", return_value="y"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        mnemosyne.prompt_stale_ffmpeg_cleanup(mnemosyne.load_ffmpeg_state())
                self.assertFalse((install_dir / ("ffmpeg.exe" if mnemosyne.IS_WINDOWS else "ffmpeg")).exists())
                reloaded = mnemosyne.load_ffmpeg_state()
                self.assertEqual(reloaded["managed_installs"], [])

    def test_runtime_validation_fixture_scenarios(self):
        scenarios_root = ROOT / "runtime_validation" if (ROOT / "runtime_validation").exists() else ROOT / "tests" / "runtime_validation"
        expected = {
            "scenario_01_60fps": 2,
            "scenario_02_360p60": 2,
            "scenario_03_multistream_mkv": 1,
            "scenario_04_recursive_bak": False,
        }
        with managed_tempdir("mnemo_test_runtime_validation_") as sandbox:
            for scenario_dir in sorted(path for path in scenarios_root.iterdir() if path.is_dir()):
                workdir = sandbox / scenario_dir.name
                shutil.copytree(scenario_dir, workdir)
                config = json.loads((scenario_dir / "config.json").read_text(encoding="utf-8"))
                videos = sorted(mnemosyne.iter_video_files(workdir, recursive=config.get("recursive", False)))
                self.assertTrue(videos, f"No input video found for {scenario_dir.name}")
                if scenario_dir.name == "scenario_04_recursive_bak":
                    with self.assertLogs(level="ERROR") as logs:
                        result = mnemosyne.process_video(1, videos[0], "libx264", config)
                    self.assertIn("Stale backup already exists", "\n".join(logs.output))
                else:
                    result = mnemosyne.process_video(1, videos[0], "libx264", config)
                self.assertEqual(result, expected[scenario_dir.name], scenario_dir.name)


# ============================================================================
# Critical Fix Regression Tests (merged from test_critical_fixes.py)
# ============================================================================

class ProcessManagerRegressionTests(unittest.TestCase):
    """Regression tests for ProcessManager race condition fix"""

    def test_kill_all_creates_snapshot_before_iteration(self):
        """Verify kill_all() creates a snapshot to avoid race conditions"""
        pm = mnemosyne.ProcessManager()
        mock_procs = [MagicMock() for _ in range(3)]
        for proc in mock_procs:
            proc.terminate = MagicMock()
            proc.wait = MagicMock()
            proc.kill = MagicMock()
            pm.register(proc)
        pm.kill_all()
        for proc in mock_procs:
            proc.terminate.assert_called_once()

    def test_kill_all_handles_concurrent_unregister(self):
        """Test that kill_all() doesn't crash when processes are unregistered concurrently"""
        pm = mnemosyne.ProcessManager()
        mock_procs = [MagicMock() for _ in range(5)]
        for proc in mock_procs:
            proc.terminate = MagicMock()
            proc.wait = MagicMock()
            proc.kill = MagicMock()
            pm.register(proc)
        def unregister_during_kill():
            time.sleep(0.01)
            pm.unregister(mock_procs[0])
        thread = threading.Thread(target=unregister_during_kill)
        thread.start()
        pm.kill_all()  # Should not raise RuntimeError
        thread.join()

    def test_kill_all_logs_exceptions(self):
        """Verify that exceptions during process termination are logged"""
        pm = mnemosyne.ProcessManager()
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = Exception("Termination failed")
        pm.register(mock_proc)
        with patch('mnemosyne.logging.warning') as mock_log:
            pm.kill_all()
            mock_log.assert_called()

    def test_kill_all_uses_kill_after_timeout(self):
        """Test that kill() is called when wait() times out"""
        pm = mnemosyne.ProcessManager()
        mock_proc = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait.side_effect = mnemosyne.subprocess.TimeoutExpired("cmd", 2)
        mock_proc.kill = MagicMock()
        pm.register(mock_proc)
        pm.kill_all()
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()


class DiskSpaceCheckRegressionTests(unittest.TestCase):
    """Regression tests for disk space check fail-safe behavior"""

    def test_has_enough_space_returns_false_on_exception(self):
        """Verify has_enough_space() returns False (fail-safe) when check fails"""
        with patch('mnemosyne.shutil.disk_usage', side_effect=Exception("Disk check failed")):
            result, free = mnemosyne.has_enough_space("/invalid/path", 1024)
            self.assertFalse(result, "Should return False on exception (fail-safe)")
            self.assertEqual(free, 0)

    def test_has_enough_space_logs_error_on_exception(self):
        """Verify that disk check failures are logged"""
        with patch('mnemosyne.shutil.disk_usage', side_effect=Exception("Disk check failed")), \
             patch('mnemosyne.logging.error') as mock_log:
            mnemosyne.has_enough_space("/invalid/path", 1024)
            mock_log.assert_called_once()
            self.assertIn("Disk space check failed", str(mock_log.call_args))

    def test_has_enough_space_returns_true_when_sufficient(self):
        """Verify normal operation when disk space is sufficient"""
        mock_usage = MagicMock()
        mock_usage.free = 10 * 1024 * 1024
        with patch('mnemosyne.shutil.disk_usage', return_value=mock_usage):
            result, free = mnemosyne.has_enough_space("/valid/path", 5 * 1024 * 1024)
            self.assertTrue(result)
            self.assertEqual(free, 10 * 1024 * 1024)

    def test_has_enough_space_returns_false_when_insufficient(self):
        """Verify returns False when disk space is insufficient"""
        mock_usage = MagicMock()
        mock_usage.free = 1 * 1024 * 1024
        with patch('mnemosyne.shutil.disk_usage', return_value=mock_usage):
            result, free = mnemosyne.has_enough_space("/valid/path", 5 * 1024 * 1024)
            self.assertFalse(result)
            self.assertEqual(free, 1 * 1024 * 1024)


class TimeoutCapRegressionTests(unittest.TestCase):
    """Regression tests for timeout cap enforcement"""

    def test_verify_media_decode_caps_timeout_at_900_seconds(self):
        """Verify that timeout is capped at 900 seconds (15 minutes)"""
        long_video_info = {"duration": 7200.0}
        with patch('mnemosyne.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            mnemosyne.verify_media_decode(Path("/fake/video.mp4"), info=long_video_info)
            call_kwargs = mock_run.call_args[1]
            self.assertLessEqual(call_kwargs['timeout'], 900,
                                "Timeout should be capped at 900 seconds")

    def test_verify_media_decode_uses_minimum_30_seconds(self):
        """Verify minimum timeout of 30 seconds for short videos"""
        short_video_info = {"duration": 1.0}
        with patch('mnemosyne.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            mnemosyne.verify_media_decode(Path("/fake/video.mp4"), info=short_video_info)
            call_kwargs = mock_run.call_args[1]
            self.assertGreaterEqual(call_kwargs['timeout'], 30,
                                   "Timeout should be at least 30 seconds")

    def test_verify_media_decode_uses_60_seconds_when_no_duration(self):
        """Verify default 60 second timeout when duration is unknown"""
        no_duration_info = {}
        with patch('mnemosyne.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            mnemosyne.verify_media_decode(Path("/fake/video.mp4"), info=no_duration_info)
            call_kwargs = mock_run.call_args[1]
            self.assertEqual(call_kwargs['timeout'], 60,
                           "Timeout should be 60 seconds when duration is unknown")

    def test_verify_media_decode_scales_timeout_with_duration(self):
        """Verify timeout scales with video duration (4x + 15s)"""
        medium_video_info = {"duration": 100.0}
        with patch('mnemosyne.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            mnemosyne.verify_media_decode(Path("/fake/video.mp4"), info=medium_video_info)
            call_kwargs = mock_run.call_args[1]
            expected_timeout = min(900, max(30, int(100.0 * 4) + 15))
            self.assertEqual(call_kwargs['timeout'], expected_timeout)


class CriticalFixIntegrationTests(unittest.TestCase):
    """Integration tests for critical fixes"""

    def test_process_manager_in_multithreaded_context(self):
        """Test ProcessManager behavior in realistic multithreaded scenario"""
        pm = mnemosyne.ProcessManager()
        def worker(worker_id):
            for i in range(5):
                mock_proc = MagicMock()
                mock_proc.terminate = MagicMock()
                mock_proc.wait = MagicMock()
                mock_proc.kill = MagicMock()
                pm.register(mock_proc)
                time.sleep(0.001)
                pm.unregister(mock_proc)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        time.sleep(0.01)
        pm.kill_all()  # Should not crash
        for t in threads:
            t.join()

    def test_disk_check_prevents_processing_when_space_low(self):
        """Verify that low disk space prevents video processing"""
        mock_usage = MagicMock()
        mock_usage.free = 100 * 1024
        with patch('mnemosyne.shutil.disk_usage', return_value=mock_usage):
            ok = mnemosyne.warn_if_space_is_low(Path("/test"), 10 * 1024 * 1024, "test")
            self.assertFalse(ok, "Should reject processing when disk space is low")


if __name__ == "__main__":
    import test_launchers

    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(test_launchers))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
