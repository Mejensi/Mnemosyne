from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path
import sys

import mnemosyne


def test_verify_download_checksum_success(monkeypatch, tmp_path):
    # create a small file
    f = tmp_path / 'a.txt'
    f.write_bytes(b'hello')
    # compute sha256
    import hashlib
    digest = hashlib.sha256(b'hello').hexdigest()
    # create fake checksum URL handler: monkeypatch download_url_to_file to write checksum content
    def fake_download_text(url):
        return digest + '  a.txt'
    monkeypatch.setattr(mnemosyne, 'download_text', fake_download_text)
    ok = mnemosyne.verify_download_checksum(f, 'http://example.com/checksums.sha256', 'sha256', 'a.txt')
    assert ok is True


def test_verify_download_checksum_failure(monkeypatch, tmp_path):
    f = tmp_path / 'a.txt'
    f.write_bytes(b'hello')
    def fake_download(url, dest, show_progress=False):
        Path(dest).write_text('deadbeef  a.txt')
        return True
    monkeypatch.setattr(mnemosyne, 'download_url_to_file', fake_download)
    ok = mnemosyne.verify_download_checksum(f, 'http://example.com/checksums.sha256', 'sha256', 'a.txt')
    assert ok is False


def test_verify_evermeet_signature_success(monkeypatch, tmp_path):
    # Create fake archive and signature
    archive = tmp_path / 'a.zip'
    sig = tmp_path / 'a.zip.sig'
    archive.write_text('archive')
    sig.write_text('sig')
    # monkeypatch subprocess.run to emulate gpg fingerprint and verify
    class Result:
        def __init__(self, returncode, stdout=''):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ''
    calls = {'fingerprint': False, 'verify': False}
    def fake_run(cmd, capture_output=False, text=False, encoding=None, timeout=None):
        s = ' '.join(cmd)
        if '--with-colons' in cmd:
            calls['fingerprint'] = True
            # include fingerprint string
            return Result(0, mnemosyne.EVERMEET_GPG_FINGERPRINT)
        if '--verify' in cmd:
            calls['verify'] = True
            return Result(0, '')
        return Result(0, '')
    monkeypatch.setattr(mnemosyne.subprocess, 'run', fake_run)
    ok = mnemosyne.verify_evermeet_signature(archive, sig)
    assert ok is True


def test_verify_evermeet_signature_failure(monkeypatch, tmp_path):
    archive = tmp_path / 'a.zip'
    sig = tmp_path / 'a.zip.sig'
    archive.write_text('archive')
    sig.write_text('sig')
    def fake_run(cmd, capture_output=False, text=False, encoding=None, timeout=None):
        s = ' '.join(cmd)
        if '--with-colons' in cmd:
            return type('R', (), {'returncode': 0, 'stdout': 'BADFINGERPRINT'})
        if '--verify' in cmd:
            return type('R', (), {'returncode': 2, 'stderr': 'bad sig'})
        return type('R', (), {'returncode': 0, 'stdout': ''})
    monkeypatch.setattr(mnemosyne.subprocess, 'run', fake_run)
    ok = mnemosyne.verify_evermeet_signature(archive, sig)
    assert ok is False
