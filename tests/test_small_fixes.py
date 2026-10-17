from __future__ import annotations

from types import SimpleNamespace

import mnemosyne


def test_powershell_download_does_not_bypass_execution_policy(monkeypatch, tmp_path):
    # An execution policy governs script files, not a -Command string, so the
    # "-ExecutionPolicy Bypass" flag does nothing useful here and only looks suspicious to antivirus tools.
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mnemosyne.subprocess, "run", fake_run)
    assert mnemosyne.powershell_download("https://example.invalid/ffmpeg.zip", tmp_path / "ffmpeg.zip") is True
    command = calls[0]
    assert command[0] == "powershell"
    assert "-NoProfile" in command
    assert "-ExecutionPolicy" not in command
    assert "Bypass" not in command


def test_get_file_metadata_prefers_birthtime_over_ctime():
    # Python 3.12 deprecated st_ctime as the Windows creation time and added st_birthtime.
    class FakePath:
        def stat(self):
            return SimpleNamespace(st_ctime=300.0, st_atime=200.0, st_mtime=100.0, st_birthtime=50.0)

    assert mnemosyne.get_file_metadata(FakePath()) == (50.0, 200.0, 100.0)


def test_get_file_metadata_falls_back_to_ctime_without_birthtime():
    class FakePath:
        def stat(self):
            return SimpleNamespace(st_ctime=300.0, st_atime=200.0, st_mtime=100.0)

    assert mnemosyne.get_file_metadata(FakePath()) == (300.0, 200.0, 100.0)


def _accept_unverified_ffmpeg(monkeypatch, base):
    """Install a fake FFmpeg pair the way 'Accept once' does and return its folder."""
    (base / "appdata").mkdir()
    monkeypatch.setattr(mnemosyne, "APP_DATA", base / "appdata")
    monkeypatch.setattr(mnemosyne, "FFMPEG_STATE_FILE", base / "appdata" / "ffmpeg_state.json")
    monkeypatch.setattr(mnemosyne, "get_launcher_dir", lambda: base / "launcher")
    monkeypatch.setattr(mnemosyne, "validate_ffmpeg_pair", lambda ffmpeg_path, ffprobe_path: True)
    install_dir = base / "bin"
    install_dir.mkdir()
    for name in mnemosyne.get_managed_ffmpeg_binary_names():
        (install_dir / name).write_text("fake binary", encoding="utf-8")
    mnemosyne.upsert_managed_ffmpeg_install(
        install_dir,
        "custom",
        "test-source",
        mnemosyne.default_ffmpeg_state(),
        verification_status="user_override_unverified",
    )
    return install_dir


def _managed_candidates():
    # Read the state back from disk, like any later call does.
    state = mnemosyne.load_ffmpeg_state()
    return [item for item in mnemosyne.iter_ffmpeg_candidate_pairs(state) if item.get("managed_entry")]


def test_unverified_ffmpeg_stays_usable_for_the_run_that_accepted_it(monkeypatch, tmp_path):
    install_dir = _accept_unverified_ffmpeg(monkeypatch, tmp_path)
    assert len(_managed_candidates()) == 1
    assert all((install_dir / name).exists() for name in mnemosyne.get_managed_ffmpeg_binary_names())


def test_unverified_ffmpeg_is_removed_when_a_later_run_starts(monkeypatch, tmp_path):
    install_dir = _accept_unverified_ffmpeg(monkeypatch, tmp_path)
    monkeypatch.setattr(mnemosyne, "SESSION_ID", "a-later-run")
    assert _managed_candidates() == []
    assert not any((install_dir / name).exists() for name in mnemosyne.get_managed_ffmpeg_binary_names())
    assert mnemosyne.load_ffmpeg_state()["managed_installs"] == []
