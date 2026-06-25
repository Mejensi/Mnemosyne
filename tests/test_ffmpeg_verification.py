from __future__ import annotations

import builtins
import json
import os
import tempfile
import shutil
from pathlib import Path
import sys
import time

import mnemosyne


def test_prompt_unverified_choice_remember(monkeypatch):
    monkeypatch.setattr(mnemosyne, 'supports_interactive_input', lambda: True)
    inputs = iter(['2'])
    monkeypatch.setattr(builtins, 'input', lambda prompt='': next(inputs))
    res = mnemosyne.prompt_unverified_ffmpeg_override(['fake: reason'])
    assert res == 'remember'


def test_record_and_check_accepted_source(tmp_path):
    # Use a temporary APP_DATA to avoid touching real home
    original_app = mnemosyne.APP_DATA
    try:
        mnemosyne.APP_DATA = tmp_path / 'appdata'
        source = {"url": "https://example.com/ffmpeg.zip", "digest": "abcd"}
        # ensure clean state
        if (mnemosyne.APP_DATA / 'ffmpeg_state.json').exists():
            (mnemosyne.APP_DATA / 'ffmpeg_state.json').unlink()
        ok = mnemosyne.record_accepted_unverified_source(source)
        assert ok is True
        assert mnemosyne.is_source_previously_accepted(source) is True
        # check persistence
        loaded = mnemosyne.load_ffmpeg_state()
        assert 'accepted_unverified' in loaded
        assert loaded['accepted_unverified'][0]['source_url'] == source['url']
    finally:
        mnemosyne.APP_DATA = original_app


def test_download_uses_previously_accepted(monkeypatch, tmp_path):
    # Monkeypatch to simulate a successful extraction/install when source is previously accepted
    original_app = mnemosyne.APP_DATA
    try:
        mnemosyne.APP_DATA = tmp_path / 'appdata'
        # prepare fake source
        fake_source = {"kind": "archive", "url": "https://example.com/ff.zip", "archive_name": "ff.zip"}
        # replace iter_platform_ffmpeg_sources to return our fake source
        monkeypatch.setattr(mnemosyne, 'iter_platform_ffmpeg_sources', lambda: [fake_source])
        # mark source as previously accepted
        monkeypatch.setattr(mnemosyne, 'is_source_previously_accepted', lambda s: True)
        # stub extract to create ffmpeg and ffprobe in stage dir
        def fake_extract(source, temp_dir, install_stage_dir, binary_names, allow_unverified=False):
            install_stage_dir.mkdir(parents=True, exist_ok=True)
            (install_stage_dir / binary_names[0]).write_text("ffmpeg-binary")
            (install_stage_dir / binary_names[1]).write_text("ffprobe-binary")
        monkeypatch.setattr(mnemosyne, 'extract_ffmpeg_source', fake_extract)
        # stub install to just move files into install dir
        def fake_install(stage, install_dir, binary_names, storage_mode, source, ffmpeg_state, verification_status='verified'):
            install_dir = Path(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            for name in binary_names:
                (install_dir / name).write_text(name)
            return True
        monkeypatch.setattr(mnemosyne, 'install_staged_ffmpeg', fake_install)
        # stub check to return True
        monkeypatch.setattr(mnemosyne, 'check_ffmpeg_with_policy', lambda policy, ffmpeg_state=None: True)
        ok = mnemosyne.download_ffmpeg(storage_mode='session', custom_install_path='', ffmpeg_state=None)
        assert ok is True
    finally:
        mnemosyne.APP_DATA = original_app
