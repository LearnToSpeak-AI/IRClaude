from pathlib import Path
from unittest import mock

import pytest

from irclaude.bridge.preflight import ClaudeStatus, check_claude


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_claude_not_installed(fake_home, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    status = check_claude(home=fake_home)
    assert status == ClaudeStatus(
        installed=False, version=None, auth_mode="none", hint=mock.ANY
    )
    assert "Install Claude Code" in status.hint


def test_subscription_auth_when_session_dir_exists(fake_home, monkeypatch):
    (fake_home / ".claude").mkdir()
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    completed = mock.Mock(returncode=0, stdout="1.0.0\n", stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: completed)
    status = check_claude(home=fake_home)
    assert status.installed is True
    assert status.auth_mode == "subscription"
    assert status.version == "1.0.0"
    assert status.hint is None


def test_api_key_auth_overrides_session(fake_home, monkeypatch):
    (fake_home / ".claude").mkdir()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=0, stdout="1.0.0\n", stderr=""),
    )
    status = check_claude(home=fake_home)
    assert status.auth_mode == "api_key"
    assert status.hint is None


def test_no_auth_when_session_missing_and_no_key(fake_home, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=0, stdout="1.0.0\n", stderr=""),
    )
    status = check_claude(home=fake_home)
    assert status.installed is True
    assert status.auth_mode == "none"
    assert "claude login" in status.hint


def test_version_parsing_handles_nonzero_exit(fake_home, monkeypatch):
    (fake_home / ".claude").mkdir()
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=1, stdout="", stderr="err"),
    )
    status = check_claude(home=fake_home)
    assert status.installed is True
    assert status.version is None
    assert status.auth_mode == "subscription"
