from unittest import mock

import pytest

from irclaude.bridge.weechat_link import (
    add_weechat_server_via_headless,
    detect_weechat_install_plan,
    install_weechat_headless,
    weechat_running,
)


def test_returns_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    ok, msg = add_weechat_server_via_headless("irclaude", "127.0.0.1", 6667)
    assert ok is False
    assert "not found" in msg
    assert "apt install weechat-headless" in msg
    assert "brew install weechat" in msg


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


def test_detect_install_plan_apt_on_debian(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/apt-get" if name == "apt-get" else None,
    )
    plan = detect_weechat_install_plan()
    assert plan is not None
    assert plan.manager == "apt"
    assert "apt-get" in plan.command
    assert "weechat-headless" in plan.command
    assert plan.command[0] == "sudo"


def test_detect_install_plan_dnf_on_fedora(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )
    plan = detect_weechat_install_plan()
    assert plan is not None
    assert plan.manager == "dnf"


def test_detect_install_plan_pacman_on_arch(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/pacman" if name == "pacman" else None,
    )
    plan = detect_weechat_install_plan()
    assert plan is not None
    assert plan.manager == "pacman"


def test_detect_install_plan_brew_on_macos(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None,
    )
    plan = detect_weechat_install_plan()
    assert plan is not None
    assert plan.manager == "brew"
    assert plan.command[0] == "brew"


def test_detect_install_plan_returns_none_on_unknown(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert detect_weechat_install_plan() is None


def test_install_weechat_headless_returns_ok_on_zero_exit(monkeypatch):
    from irclaude.bridge.weechat_link import PackageInstallPlan
    plan = PackageInstallPlan("apt", ("sudo", "apt-get", "install", "-y", "weechat-headless"))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=0),
    )
    ok, msg = install_weechat_headless(plan)
    assert ok is True
    assert "apt" in msg


def test_install_weechat_headless_returns_failure_on_nonzero_exit(monkeypatch):
    from irclaude.bridge.weechat_link import PackageInstallPlan
    plan = PackageInstallPlan("apt", ("sudo", "apt-get", "install", "-y", "weechat-headless"))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: mock.Mock(returncode=100),
    )
    ok, msg = install_weechat_headless(plan)
    assert ok is False
    assert "100" in msg
