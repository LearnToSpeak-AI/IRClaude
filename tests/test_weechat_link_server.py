from unittest import mock

import pytest

from irclaude.bridge.weechat_link import add_weechat_server_via_headless, weechat_running


def test_returns_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    ok, msg = add_weechat_server_via_headless("irclaude", "127.0.0.1", 6667)
    assert ok is False
    assert "not found" in msg


def test_invokes_headless_with_no_tls_autoconnect(monkeypatch):
    captured: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout):
        captured.append(cmd)
        return mock.Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/weechat-headless")
    monkeypatch.setattr("subprocess.run", fake_run)
    ok, msg = add_weechat_server_via_headless("irclaude", "127.0.0.1", 6667)
    assert ok is True
    assert "added to WeeChat" in msg
    assert captured, "expected weechat-headless invocation"
    cmd = captured[0]
    assert cmd[0] == "/usr/bin/weechat-headless"
    assert cmd[1] == "--run-command"
    payload = cmd[2]
    assert "/server add irclaude 127.0.0.1/6667" in payload
    assert "-notls" in payload
    assert "-autoconnect" in payload
    assert "/save" in payload
    assert "/quit" in payload


def test_already_exists_is_treated_as_success(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/weechat-headless")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(
            returncode=1, stdout="", stderr="server name 'irclaude' already exists"
        ),
    )
    ok, msg = add_weechat_server_via_headless("irclaude", "127.0.0.1", 6667)
    assert ok is True
    assert "already configured" in msg


def test_other_failure_is_reported(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/weechat-headless")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=2, stdout="", stderr="boom"),
    )
    ok, msg = add_weechat_server_via_headless("irclaude", "127.0.0.1", 6667)
    assert ok is False
    assert "exit=2" in msg
    assert "boom" in msg


def test_subprocess_exception_is_reported(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/weechat-headless")

    def raise_exc(*a, **kw):
        raise OSError("permission denied")

    monkeypatch.setattr("subprocess.run", raise_exc)
    ok, msg = add_weechat_server_via_headless("irclaude", "127.0.0.1", 6667)
    assert ok is False
    assert "permission denied" in msg


def test_weechat_running_false_without_pgrep(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert weechat_running() is False


def test_weechat_running_true_when_pgrep_finds_process(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pgrep")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=0, stdout="1234\n", stderr=""),
    )
    assert weechat_running() is True


def test_weechat_running_false_when_pgrep_finds_nothing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pgrep")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=1, stdout="", stderr=""),
    )
    assert weechat_running() is False
