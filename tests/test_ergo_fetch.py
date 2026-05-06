import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from irclaude.bridge.ergo_fetch import download_ergo, parse_version_pin


def _build_fake_tarball(binary_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="ergo-2.16.0/ergo")
        info.size = len(binary_bytes)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(binary_bytes))
    return buf.getvalue()


def test_parse_version_pin(tmp_path: Path):
    pin = tmp_path / ".ergo-version"
    pin.write_text("version=2.16.0\nsha256=deadbeef\n", encoding="utf-8")
    info = parse_version_pin(pin)
    assert info.version == "2.16.0"
    assert info.sha256 == "deadbeef"


def test_download_ergo_extracts_binary(tmp_path: Path, monkeypatch):
    binary = b"#!/bin/sh\necho fake-ergo\n"
    tar_bytes = _build_fake_tarball(binary)
    sha = hashlib.sha256(tar_bytes).hexdigest()

    def fake_urlopen(url, timeout=60):
        assert url.endswith("ergo-2.16.0-linux-x86_64.tar.gz")

        class _R:
            def read(self_inner):
                return tar_bytes

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _R()

    monkeypatch.setattr(
        "irclaude.bridge.ergo_fetch.urlopen", fake_urlopen, raising=False
    )

    target = tmp_path / "bin"
    path = download_ergo(target_dir=target, version="2.16.0", expected_sha256=sha)
    assert path == target / "ergo"
    assert path.read_bytes() == binary
    assert path.stat().st_mode & 0o111  # executable


def test_download_ergo_skips_when_already_present(tmp_path: Path, monkeypatch):
    target = tmp_path / "bin"
    target.mkdir()
    existing = target / "ergo"
    existing.write_bytes(b"already here")
    sha = hashlib.sha256(b"already here").hexdigest()

    def fake_urlopen(*a, **kw):  # pragma: no cover - must not be called
        raise AssertionError("network must not be hit")

    monkeypatch.setattr(
        "irclaude.bridge.ergo_fetch.urlopen", fake_urlopen, raising=False
    )
    path = download_ergo(target_dir=target, version="2.16.0", expected_sha256=sha)
    assert path.read_bytes() == b"already here"


def test_download_ergo_rejects_bad_checksum(tmp_path: Path, monkeypatch):
    binary = b"junk"
    tar_bytes = _build_fake_tarball(binary)

    def fake_urlopen(url, timeout=60):
        class _R:
            def read(self_inner):
                return tar_bytes

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _R()

    monkeypatch.setattr(
        "irclaude.bridge.ergo_fetch.urlopen", fake_urlopen, raising=False
    )
    with pytest.raises(ValueError, match="sha256 mismatch"):
        download_ergo(
            target_dir=tmp_path / "bin",
            version="2.16.0",
            expected_sha256="0" * 64,
        )
