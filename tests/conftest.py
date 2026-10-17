from pathlib import Path
import sys

import pytest

# Repo root on sys.path so tests can `import mnemosyne` (the single-file script).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mnemosyne  # noqa: E402  (needs the sys.path line above)


def redirect_mnemosyne_paths(monkeypatch, root: Path):
    """Send everything Mnemosyne writes (settings, FFmpeg state, FFmpeg installs, logs) under `root`."""
    app_data = root / "appdata"
    launcher_dir = root / "launcher"
    app_data.mkdir(parents=True, exist_ok=True)
    launcher_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mnemosyne, "APP_DATA", app_data)
    monkeypatch.setattr(mnemosyne, "LOG_DIR", app_data / "logs")
    monkeypatch.setattr(mnemosyne, "BIN_DIR", app_data / "bin")
    monkeypatch.setattr(mnemosyne, "APP_CONFIG_FILE", app_data / "config.json")
    monkeypatch.setattr(mnemosyne, "FFMPEG_STATE_FILE", app_data / "ffmpeg_state.json")
    # get_runtime_dir() (session FFmpeg, gpg scratch folders, the log file) hangs off this.
    monkeypatch.setattr(mnemosyne, "get_launcher_dir", lambda: launcher_dir)


@pytest.fixture(scope="session", autouse=True)
def isolate_mnemosyne_for_session(tmp_path_factory):
    """Covers code that runs outside a single test, such as setUpClass.

    Without this, running the tests overwrites the developer's real FFmpeg state
    (~/.mnemosyne/ffmpeg_state.json), saved settings, and the ffmpeg/ffprobe files
    that live in the .mnemosyne_runtime folder next to mnemosyne.py.
    """
    with pytest.MonkeyPatch.context() as monkeypatch:
        redirect_mnemosyne_paths(monkeypatch, tmp_path_factory.mktemp("mnemosyne_session"))
        yield


@pytest.fixture(autouse=True)
def isolate_mnemosyne_per_test(tmp_path, monkeypatch):
    """Fresh, empty Mnemosyne folders for every test, so no test sees another test's files."""
    redirect_mnemosyne_paths(monkeypatch, tmp_path / "mnemosyne_isolated")
    yield
