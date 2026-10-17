from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

import mnemosyne


@contextlib.contextmanager
def managed_tempdir(prefix: str):
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        base = Path(temp_dir)
        try:
            yield base
        finally:
            mnemosyne.cleanup_temp_files(base, recursive=True, include_current_session=True)


def write_launcher_smoke_stub(path: Path):
    path.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "target = Path(os.environ['MNEMOSYNE_TEST_OUTPUT'])\n"
        "target.write_text(json.dumps({\n"
        "    'args': sys.argv[1:],\n"
        "    'launcher_dir': os.environ.get('MNEMOSYNE_LAUNCHER_DIR', ''),\n"
        "}, ensure_ascii=False), encoding='utf-8')\n"
        "print('LAUNCHER_SMOKE_OK')\n",
        encoding="utf-8",
    )


def write_windows_python_shim(path: Path):
    path.write_text(
        "@echo off\n"
        f"\"{sys.executable}\" %*\n",
        encoding="utf-8",
    )


def write_fake_version_binary(path: Path, version_line: str, marker_path: Path):
    if mnemosyne.IS_WINDOWS:
        path.write_text(
            "@echo off\n"
            f">> \"{marker_path}\" echo called\n"
            f"echo {version_line}\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "#!/usr/bin/env sh\n"
            f"printf 'called\\n' >> '{marker_path.as_posix()}'\n"
            f"printf '%s\\n' '{version_line}'\n",
            encoding="utf-8",
        )
        path.chmod(0o755)


def probe_bash():
    bash_path = shutil.which("bash")
    if not bash_path:
        return None, "bash is not available"
    probe = subprocess.run(
        [bash_path, "-lc", "printf BASH_OK"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if probe.returncode != 0 or "BASH_OK" not in probe.stdout:
        return None, f"bash is present but not runnable in this environment: {probe.stderr.strip()}"
    return bash_path, None


class MnemosyneLauncherTests(unittest.TestCase):
    def test_check_ffmpeg_rejects_system_path_when_policy_prompt_declines(self):
        with managed_tempdir("mnemo_test_system_ffmpeg_prompt_") as base:
            marker = base / "system_ffmpeg_marker.txt"
            ffmpeg = base / ("ffmpeg.bat" if mnemosyne.IS_WINDOWS else "ffmpeg")
            ffprobe = base / ("ffprobe.bat" if mnemosyne.IS_WINDOWS else "ffprobe")
            write_fake_version_binary(ffmpeg, "ffmpeg version fake", marker)
            write_fake_version_binary(ffprobe, "ffprobe version fake", marker)
            candidate = {
                "ffmpeg_path": ffmpeg,
                "ffprobe_path": ffprobe,
                "origin": "system",
                "label": "PATH",
            }
            with patch.object(mnemosyne, "iter_ffmpeg_candidate_pairs", return_value=iter([candidate])), patch.object(
                mnemosyne, "supports_interactive_input", return_value=True
            ), patch("builtins.input", return_value="n"), patch.object(
                mnemosyne, "FFMPEG_CMD", mnemosyne.FFMPEG_CMD
            ), patch.object(mnemosyne, "FFPROBE_CMD", mnemosyne.FFPROBE_CMD):
                self.assertFalse(mnemosyne.check_ffmpeg_with_policy("prompt"))
            self.assertFalse(marker.exists())

    def test_check_ffmpeg_allows_system_path_when_policy_allows(self):
        with managed_tempdir("mnemo_test_system_ffmpeg_allow_") as base:
            marker = base / "system_ffmpeg_marker.txt"
            ffmpeg = base / ("ffmpeg.bat" if mnemosyne.IS_WINDOWS else "ffmpeg")
            ffprobe = base / ("ffprobe.bat" if mnemosyne.IS_WINDOWS else "ffprobe")
            write_fake_version_binary(ffmpeg, "ffmpeg version fake", marker)
            write_fake_version_binary(ffprobe, "ffprobe version fake", marker)
            candidate = {
                "ffmpeg_path": ffmpeg,
                "ffprobe_path": ffprobe,
                "origin": "system",
                "label": "PATH",
            }
            with patch.object(mnemosyne, "iter_ffmpeg_candidate_pairs", return_value=iter([candidate])), patch.object(
                mnemosyne, "FFMPEG_CMD", mnemosyne.FFMPEG_CMD
            ), patch.object(mnemosyne, "FFPROBE_CMD", mnemosyne.FFPROBE_CMD):
                self.assertTrue(mnemosyne.check_ffmpeg_with_policy("allow"))
            self.assertTrue(marker.exists())
            self.assertGreaterEqual(len(marker.read_text(encoding="utf-8").splitlines()), 2)

    def test_check_ffmpeg_rejects_system_path_when_policy_denies(self):
        with managed_tempdir("mnemo_test_system_ffmpeg_deny_") as base:
            marker = base / "system_ffmpeg_marker.txt"
            ffmpeg = base / ("ffmpeg.bat" if mnemosyne.IS_WINDOWS else "ffmpeg")
            ffprobe = base / ("ffprobe.bat" if mnemosyne.IS_WINDOWS else "ffprobe")
            write_fake_version_binary(ffmpeg, "ffmpeg version fake", marker)
            write_fake_version_binary(ffprobe, "ffprobe version fake", marker)
            candidate = {
                "ffmpeg_path": ffmpeg,
                "ffprobe_path": ffprobe,
                "origin": "system",
                "label": "PATH",
            }
            with patch.object(mnemosyne, "iter_ffmpeg_candidate_pairs", return_value=iter([candidate])), patch.object(
                mnemosyne, "FFMPEG_CMD", mnemosyne.FFMPEG_CMD
            ), patch.object(mnemosyne, "FFPROBE_CMD", mnemosyne.FFPROBE_CMD):
                self.assertFalse(mnemosyne.check_ffmpeg_with_policy("deny"))
            self.assertFalse(marker.exists())

    def test_iter_ffmpeg_candidate_pairs_rejects_split_path_pairs(self):
        with managed_tempdir("mnemo_test_split_path_pair_") as base:
            ffmpeg_dir = base / "ffmpeg_dir"
            ffprobe_dir = base / "ffprobe_dir"
            ffmpeg_dir.mkdir()
            ffprobe_dir.mkdir()
            ffmpeg_path = ffmpeg_dir / ("ffmpeg.bat" if mnemosyne.IS_WINDOWS else "ffmpeg")
            ffprobe_path = ffprobe_dir / ("ffprobe.bat" if mnemosyne.IS_WINDOWS else "ffprobe")
            ffmpeg_path.write_text("@echo off\n" if mnemosyne.IS_WINDOWS else "#!/usr/bin/env sh\n", encoding="utf-8")
            ffprobe_path.write_text("@echo off\n" if mnemosyne.IS_WINDOWS else "#!/usr/bin/env sh\n", encoding="utf-8")
            if not mnemosyne.IS_WINDOWS:
                ffmpeg_path.chmod(0o755)
                ffprobe_path.chmod(0o755)
            with patch.object(mnemosyne, "get_launcher_dir", return_value=base / "missing_launcher"), patch.object(
                mnemosyne, "get_script_dir", return_value=base / "missing_script"
            ), patch.object(
                mnemosyne, "BIN_DIR", base / "missing_app_bin"
            ), patch(
                "mnemosyne.shutil.which", side_effect=[str(ffmpeg_path), str(ffprobe_path)]
            ):
                candidates = list(mnemosyne.iter_ffmpeg_candidate_pairs())
            self.assertFalse(any(candidate["origin"] == "system" for candidate in candidates))

    def test_ensure_ffmpeg_auto_downloads_when_missing(self):
        with patch.object(mnemosyne, "check_ffmpeg_with_policy", return_value=False), patch.object(
            mnemosyne, "download_ffmpeg", return_value=True
        ) as download_mock, patch("builtins.input") as input_mock:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(mnemosyne.ensure_ffmpeg(auto_download=True))
        download_mock.assert_called_once()
        input_mock.assert_not_called()

    def test_ensure_ffmpeg_manual_mode_can_decline_download(self):
        with patch.object(mnemosyne, "check_ffmpeg_with_policy", return_value=False), patch.object(
            mnemosyne, "download_ffmpeg", return_value=True
        ) as download_mock, patch("builtins.input", return_value="n"):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(mnemosyne.ensure_ffmpeg(auto_download=False))
        download_mock.assert_not_called()

    def test_install_staged_ffmpeg_installs_and_records_state(self):
        with managed_tempdir("mnemo_test_download_ffmpeg_") as base:
            stage_dir = base / "stage"
            install_dir = base / "app_bin"
            stage_dir.mkdir()
            binary_names = ["ffmpeg.exe", "ffprobe.exe"] if mnemosyne.IS_WINDOWS else ["ffmpeg", "ffprobe"]
            for binary_name in binary_names:
                (stage_dir / binary_name).write_text(f"fake {binary_name}", encoding="utf-8")
            state = mnemosyne.default_ffmpeg_state()
            install_calls: list[tuple[Path, list[str], Path]] = []

            def fake_install(incoming_stage_dir, incoming_binary_names, incoming_install_dir=None):
                install_calls.append((Path(incoming_stage_dir), list(incoming_binary_names), Path(incoming_install_dir)))

            with patch.object(mnemosyne, "validate_staged_ffmpeg_install", return_value=True), patch.object(
                mnemosyne, "install_binaries_atomically", side_effect=fake_install
            ), patch.object(mnemosyne, "FFMPEG_STATE_FILE", base / "ffmpeg_state.json"):
                mnemosyne.install_staged_ffmpeg(
                    stage_dir,
                    install_dir,
                    binary_names,
                    "appdata",
                    {"url": "https://example.invalid/ffmpeg"},
                    state,
                )

            self.assertEqual(install_calls, [(stage_dir, binary_names, install_dir)])
            self.assertEqual(state["managed_installs"][0]["install_path"], str(install_dir.resolve()))

    def test_download_manifest_rejects_digest_mismatch(self):
        with managed_tempdir("mnemo_test_download_digest_fail_") as base:
            archive = base / "payload.zip"
            archive.write_bytes(b"payload")
            source = {"checksum_algorithm": "sha256", "digest": "deadbeef"}
            self.assertFalse(mnemosyne.verify_download_manifest_entry(archive, source))

    def test_platform_sources_are_iterated_in_order(self):
        source = {
            platform.system(): [
                {"url": "https://example.invalid/bad"},
                {"url": "https://example.invalid/good"},
            ]
        }
        with patch.object(mnemosyne, "DEFAULT_FFMPEG_DOWNLOADS", source):
            sources = list(mnemosyne.iter_platform_ffmpeg_sources())
        self.assertEqual([item["url"] for item in sources], ["https://example.invalid/bad", "https://example.invalid/good"])

    def test_noninteractive_mode_blocks_unverified_override(self):
        with patch.object(mnemosyne, "supports_interactive_input", return_value=False):
            self.assertFalse(mnemosyne.prompt_unverified_ffmpeg_override(["checksum verification failed"]))

    def test_unverified_override_declines_on_negative_input(self):
        with patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch(
            "builtins.input", return_value="3"
        ):
            self.assertFalse(mnemosyne.prompt_unverified_ffmpeg_override(["checksum verification failed"]))

    def test_unverified_stage_validation_blocks_install(self):
        with managed_tempdir("mnemo_test_override_stage_") as base:
            stage_dir = base / "stage"
            stage_dir.mkdir()
            with patch.object(mnemosyne, "validate_ffmpeg_pair", return_value=False), patch.object(
                mnemosyne, "install_binaries_atomically"
            ) as install_mock:
                self.assertFalse(mnemosyne.validate_staged_ffmpeg_install(stage_dir, ["ffmpeg", "ffprobe"]))
            install_mock.assert_not_called()

    def test_unverified_install_state_is_recorded(self):
        with managed_tempdir("mnemo_test_unverified_state_") as base:
            state = mnemosyne.default_ffmpeg_state()
            install_dir = base / "bin"
            install_dir.mkdir()
            with patch.object(mnemosyne, "FFMPEG_STATE_FILE", base / "ffmpeg_state.json"):
                mnemosyne.upsert_managed_ffmpeg_install(
                    install_dir,
                    "custom",
                    "test-source",
                    state,
                    verification_status="user_override_unverified",
                )
                reloaded = mnemosyne.load_ffmpeg_state()
            self.assertEqual(reloaded["managed_installs"][0]["verification_status"], "user_override_unverified")

    def test_unverified_managed_install_is_removed_when_validation_fails(self):
        with managed_tempdir("mnemo_test_unverified_prune_") as base:
            install_dir = base / "bin"
            install_dir.mkdir()
            for binary_name in mnemosyne.get_managed_ffmpeg_binary_names():
                (install_dir / binary_name).write_text("bad", encoding="utf-8")
            state = mnemosyne.default_ffmpeg_state()
            state["managed_installs"] = [
                {
                    "install_path": str(install_dir),
                    "storage_mode": "custom",
                    "source_identity": "unverified-test",
                    "created_at": int(time.time()),
                    "last_used_at": int(time.time()),
                    "verification_status": "user_override_unverified",
                    "last_validation_error": "",
                }
            ]
            with patch.object(mnemosyne, "FFMPEG_STATE_FILE", base / "state.json"), patch.object(
                mnemosyne, "validate_ffmpeg_pair", return_value=False
            ):
                candidates = list(mnemosyne.iter_ffmpeg_candidate_pairs(state))
            self.assertFalse(any(candidate.get("managed_entry") for candidate in candidates))
            self.assertFalse(any((install_dir / name).exists() for name in mnemosyne.get_managed_ffmpeg_binary_names()))

    def test_verify_download_manifest_entry_accepts_checksum_url(self):
        with managed_tempdir("mnemo_test_checksum_url_ok_") as base:
            archive = base / "payload.tar.xz"
            archive.write_bytes(b"payload")
            digest = mnemosyne.compute_file_digest(archive, "sha256")
            source = {
                "archive_name": archive.name,
                "checksum_algorithm": "sha256",
                "checksum_url": "https://example.invalid/checksums.sha256",
                "checksum_name": archive.name,
            }
            with patch.object(mnemosyne, "download_text", return_value=f"{digest}  {archive.name}\n"):
                self.assertTrue(mnemosyne.verify_download_manifest_entry(archive, source))

    def test_verify_download_manifest_entry_rejects_missing_checksum_entry(self):
        with managed_tempdir("mnemo_test_checksum_url_missing_") as base:
            archive = base / "payload.tar.xz"
            archive.write_bytes(b"payload")
            source = {
                "archive_name": archive.name,
                "checksum_algorithm": "sha256",
                "checksum_url": "https://example.invalid/checksums.sha256",
                "checksum_name": archive.name,
            }
            with patch.object(mnemosyne, "download_text", return_value="deadbeef  other.tar.xz\n"):
                self.assertFalse(mnemosyne.verify_download_manifest_entry(archive, source))

    def test_validate_ffmpeg_download_sources_accepts_checksum_url_without_digest(self):
        mnemosyne.validate_ffmpeg_download_sources(
            {
                "Linux": {
                    "kind": "archive",
                    "url": "https://example.invalid/ffmpeg.tar.xz",
                    "archive_name": "ffmpeg.tar.xz",
                    "checksum_algorithm": "sha256",
                    "checksum_url": "https://example.invalid/checksums.sha256",
                    "checksum_name": "ffmpeg.tar.xz",
                }
            }
        )

    def test_validate_ffmpeg_download_sources_requires_integrity_metadata(self):
        with self.assertRaises(ValueError):
            mnemosyne.validate_ffmpeg_download_sources(
                {
                    "Linux": {
                        "kind": "archive",
                        "url": "https://example.invalid/ffmpeg.tar.xz",
                        "archive_name": "ffmpeg.tar.xz",
                        "checksum_algorithm": "sha256",
                    }
                }
            )

    def test_platform_binary_names_for_release_targets(self):
        expected = {
            "Windows": ["ffmpeg.exe", "ffprobe.exe"],
            "Linux": ["ffmpeg", "ffprobe"],
            "Darwin": ["ffmpeg", "ffprobe"],
        }
        for system_name, binary_names in expected.items():
            with patch.object(mnemosyne, "IS_WINDOWS", system_name == "Windows"):
                self.assertEqual(mnemosyne.get_managed_ffmpeg_binary_names(), binary_names)

    def test_release_payload_is_minimal_launcher_trio(self):
        release_payload = {"mnemosyne.py", "mnemosyne.bat", "mnemosyne.sh"}
        for filename in release_payload:
            self.assertTrue((ROOT / filename).exists())
        self.assertNotIn("sync_wrappers.py", release_payload)
        self.assertNotIn("ffmpeg_sources.json", release_payload)
        self.assertNotIn("tests", release_payload)

    def test_darwin_app_paths_use_home_mnemosyne(self):
        with patch.object(mnemosyne.platform, "system", return_value="Darwin"), patch.object(
            mnemosyne, "IS_WINDOWS", False
        ), patch.object(Path, "home", return_value=Path("/Users/tester")):
            app_data = Path.home() / ".mnemosyne"
            self.assertEqual(app_data, Path("/Users/tester/.mnemosyne"))
            self.assertEqual(mnemosyne.get_managed_ffmpeg_binary_names(), ["ffmpeg", "ffprobe"])

    def test_darwin_download_without_source_returns_empty(self):
        with patch.object(mnemosyne.platform, "system", return_value="Darwin"), patch.object(
            mnemosyne, "DEFAULT_FFMPEG_DOWNLOADS", {}
        ):
            sources = list(mnemosyne.iter_platform_ffmpeg_sources())
        self.assertEqual(sources, [])

    def test_unverified_override_accepts_once_choice(self):
        with patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch(
            "builtins.input", return_value="1"
        ):
            self.assertEqual(mnemosyne.prompt_unverified_ffmpeg_override(["signature download failed"]), "once")

    def test_unverified_override_declines_choice(self):
        with patch.object(mnemosyne, "supports_interactive_input", return_value=True), patch(
            "builtins.input", return_value="2"
        ):
            self.assertFalse(mnemosyne.prompt_unverified_ffmpeg_override(["signature download failed"]))

    def test_host_environment_can_use_system_ffmpeg_when_allowed(self):
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            self.skipTest("FFmpeg/FFprobe are not installed on this machine")
        with patch.object(mnemosyne, "FFMPEG_CMD", mnemosyne.FFMPEG_CMD), patch.object(
            mnemosyne, "FFPROBE_CMD", mnemosyne.FFPROBE_CMD
        ):
            self.assertTrue(mnemosyne.check_ffmpeg_with_policy("allow"))
            self.assertTrue(Path(mnemosyne.FFMPEG_CMD).exists())
            self.assertTrue(Path(mnemosyne.FFPROBE_CMD).exists())

    def test_macos_evermeet_asset_download_requires_all_signatures(self):
        source = {
            "kind": "evermeet",
            "assets": [
                {
                    "binary_name": name,
                    "archive_name": f"{name}.zip",
                    "signature_name": f"{name}.zip.sig",
                    "url": f"https://example.invalid/{name}.zip",
                    "signature_url": f"https://example.invalid/{name}.zip.sig",
                }
                for name in ("ffmpeg", "ffprobe")
            ],
        }

        def fake_download(url, dest, show_progress=False):
            if url.endswith("ffprobe.zip.sig"):
                return False  # the second signature cannot be fetched
            Path(dest).write_bytes(b"data")
            return True

        with managed_tempdir("mnemo_test_evermeet_sigs_") as base:
            with patch.object(mnemosyne, "download_url_to_file", side_effect=fake_download), patch.object(
                mnemosyne, "download_text", return_value=""
            ), patch.object(mnemosyne, "verify_evermeet_signature", return_value=True), patch.object(
                mnemosyne, "extract_binaries_from_archive"
            ) as extract_mock:
                with self.assertRaises(RuntimeError) as raised:
                    mnemosyne.extract_ffmpeg_source(source, base, base / "stage", ["ffmpeg", "ffprobe"])
        self.assertIn("signature download failed for ffprobe", str(raised.exception))
        # Only the first binary (whose signature was fine) may be extracted.
        extract_mock.assert_called_once()

    def test_ffmpeg_source_manifest_is_pinned(self):
        manifest = mnemosyne.DEFAULT_FFMPEG_DOWNLOADS
        for platform_name in ("Windows", "Linux"):
            sources = manifest[platform_name]
            if isinstance(sources, dict):
                sources = [sources]
            for source in sources:
                self.assertEqual(source["kind"], "archive")
                self.assertTrue(source["checksum_url"])
                self.assertTrue(source["checksum_name"])
        self.assertEqual(manifest["Darwin"]["kind"], "evermeet")

    def test_readme_documents_drag_and_drop_mode(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Drag-and-Drop", readme)

    def test_windows_launcher_requires_adjacent_python_runtime(self):
        bat_text = (ROOT / "mnemosyne.bat").read_text(encoding="utf-8")
        self.assertIn('set "MNEMOSYNE_LAUNCHER_DIR=%~dp0"', bat_text)
        self.assertIn('set "MNEMOSYNE_APP=%~dp0mnemosyne.py"', bat_text)
        self.assertIn('if not exist "%MNEMOSYNE_APP%" (', bat_text)
        self.assertIn('mnemosyne.py is required', bat_text)
        self.assertIn('set "PYTHON_CMD="', bat_text)
        self.assertIn('py -3', bat_text)
        self.assertIn('%PYTHON_CMD% -X utf8 "%MNEMOSYNE_APP%" %*', bat_text)
        self.assertIn('if defined MNEMOSYNE_NO_PAUSE goto :NoPause', bat_text)
        self.assertNotIn("REM#PY#", bat_text)
        self.assertNotIn("TEMP_PY", bat_text)

    def test_unix_launcher_exports_launcher_dir_and_prefers_external_python(self):
        sh_text = (ROOT / "mnemosyne.sh").read_text(encoding="utf-8")
        self.assertIn('export MNEMOSYNE_LAUNCHER_DIR="$SCRIPT_DIR"', sh_text)
        self.assertIn('python3 "$SCRIPT_DIR/mnemosyne.py" "$@"', sh_text)
        self.assertNotIn("PY_EOF", sh_text)
        self.assertIn("mnemosyne.py is required", sh_text)

    def test_python_entrypoint_help_smoke(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "mnemosyne.py"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout.lower())

    @unittest.skipUnless(mnemosyne.IS_WINDOWS, "Windows launcher smoke test requires Windows")
    def test_windows_launcher_subprocess_smoke(self):
        with managed_tempdir("mnemo_test_bat_smoke_") as base:
            temp_root = base / "bat_case"
            temp_root.mkdir()
            bat_path = temp_root / "mnemosyne.bat"
            py_path = temp_root / "mnemosyne.py"
            result_path = temp_root / "launcher_result.json"

            shutil.copy(ROOT / "mnemosyne.bat", bat_path)
            write_launcher_smoke_stub(py_path)

            env = os.environ.copy()
            env["MNEMOSYNE_TEST_OUTPUT"] = str(result_path)
            env["MNEMOSYNE_NO_PAUSE"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                ["cmd", "/c", "call", str(bat_path), "--smoke", "alpha"],
                cwd=temp_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result_path.exists())
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["args"], ["--smoke", "alpha"])
            self.assertEqual(Path(payload["launcher_dir"]).resolve(), temp_root.resolve())
            self.assertIn("LAUNCHER_SMOKE_OK", result.stdout)

    @unittest.skipUnless(mnemosyne.IS_WINDOWS, "Windows launcher smoke test requires Windows")
    def test_windows_launcher_keeps_exclamation_marks_in_arguments(self):
        with managed_tempdir("mnemo_test_bat_bang_") as base:
            temp_root = base / "bat_case"
            temp_root.mkdir()
            bat_path = temp_root / "mnemosyne.bat"
            py_path = temp_root / "mnemosyne.py"
            result_path = temp_root / "launcher_result.json"

            shutil.copy(ROOT / "mnemosyne.bat", bat_path)
            write_launcher_smoke_stub(py_path)

            env = os.environ.copy()
            env["MNEMOSYNE_TEST_OUTPUT"] = str(result_path)
            env["MNEMOSYNE_NO_PAUSE"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                ["cmd", "/c", "call", str(bat_path), "Wow!.mp4"],
                cwd=temp_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["args"], ["Wow!.mp4"])

    @unittest.skipUnless(mnemosyne.IS_WINDOWS, "Windows launcher missing runtime test requires Windows")
    def test_windows_launcher_missing_python_runtime_smoke(self):
        with managed_tempdir("mnemo_test_bat_missing_runtime_") as base:
            temp_root = base / "bat_missing_runtime"
            temp_root.mkdir()
            bat_path = temp_root / "mnemosyne.bat"
            shutil.copy(ROOT / "mnemosyne.bat", bat_path)

            env = os.environ.copy()
            env["MNEMOSYNE_NO_PAUSE"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            result = subprocess.run(
                ["cmd", "/c", "call", str(bat_path), "dropped-video.mp4"],
                cwd=temp_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("mnemosyne.py is required", result.stdout)
            self.assertIn("only a launcher", result.stdout)

    @unittest.skipUnless(mnemosyne.IS_WINDOWS, "Windows launcher FFmpeg bootstrap test requires Windows")
    def test_windows_launcher_missing_ffmpeg_decline_smoke(self):
        with managed_tempdir("mnemo_test_bat_missing_ffmpeg_") as base:
            temp_root = base / "bat_missing_case"
            temp_root.mkdir()
            bat_path = temp_root / "mnemosyne.bat"
            py_path = temp_root / "mnemosyne.py"
            real_py_path = temp_root / "mnemosyne_real.py"
            result_path = temp_root / "ffmpeg_missing_result.json"

            shutil.copy(ROOT / "mnemosyne.bat", bat_path)
            shutil.copy(ROOT / "mnemosyne.py", real_py_path)
            py_path.write_text(
                "import importlib.util, json, os, sys\n"
                "from pathlib import Path\n"
                f"real_path = Path(r\"{real_py_path}\")\n"
                "spec = importlib.util.spec_from_file_location('mnemosyne_real', real_path)\n"
                "module = importlib.util.module_from_spec(spec)\n"
                "assert spec.loader is not None\n"
                "spec.loader.exec_module(module)\n"
                "module.ensure_utf8_stdio()\n"
                "module.check_ffmpeg = lambda: False\n"
                "result = module.ensure_ffmpeg(auto_download=False)\n"
                "Path(os.environ['MNEMOSYNE_TEST_OUTPUT']).write_text(json.dumps({'result': result}), encoding='utf-8')\n"
                "raise SystemExit(0 if result else 1)\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["APPDATA"] = str(temp_root / "appdata")
            system32 = Path(env.get("SystemRoot", r"C:\Windows")) / "System32"
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + str(system32)
            env["MNEMOSYNE_TEST_OUTPUT"] = str(result_path)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["MNEMOSYNE_NO_PAUSE"] = "1"

            result = subprocess.run(
                ["cmd", "/c", "call", str(bat_path)],
                cwd=temp_root,
                input="n\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(result_path.exists())
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["result"])
            self.assertIn("FFmpeg Not Found", result.stdout)
            self.assertIn("FFmpeg could not be downloaded or found", result.stdout)
            self.assertFalse((Path(env["APPDATA"]) / mnemosyne.APP_NAME / "bin").exists())

    def test_unix_launcher_subprocess_smoke(self):
        bash_path, reason = probe_bash()
        if not bash_path:
            self.skipTest(reason)

        with managed_tempdir("mnemo_test_sh_smoke_") as base:
            temp_root = base / "sh_case"
            temp_root.mkdir()
            sh_path = temp_root / "mnemosyne.sh"
            py_path = temp_root / "mnemosyne.py"
            result_path = temp_root / "launcher_result.json"
            shim_dir = temp_root / "shim_bin"
            shim_dir.mkdir()

            shutil.copy(ROOT / "mnemosyne.sh", sh_path)
            write_launcher_smoke_stub(py_path)

            python3_shim = shim_dir / "python3"
            python3_shim.write_text(
                "#!/usr/bin/env bash\n"
                f"\"{Path(sys.executable).as_posix()}\" \"$@\"\n",
                encoding="utf-8",
            )
            python3_shim.chmod(0o755)

            env = os.environ.copy()
            env["MNEMOSYNE_TEST_OUTPUT"] = str(result_path)
            env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", "")
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            result = subprocess.run(
                [bash_path, "./mnemosyne.sh", "--smoke", "beta"],
                cwd=temp_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(result_path.exists())
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["args"], ["--smoke", "beta"])
            self.assertTrue(payload["launcher_dir"])
            self.assertTrue(payload["launcher_dir"].replace("\\", "/").rstrip("/").endswith(temp_root.name))
            self.assertIn("LAUNCHER_SMOKE_OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
