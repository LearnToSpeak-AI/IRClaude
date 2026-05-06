from pathlib import Path

from typer.testing import CliRunner

from irclaude.cli import app


runner = CliRunner()


def test_up_errors_when_ergo_binary_missing(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("irclaude.cli.shutil.which", lambda name: "/usr/bin/weechat")

    result = runner.invoke(app, ["up"])
    assert result.exit_code == 1
    assert "ergo binary not found" in result.stdout
    assert "irclaude setup" in result.stdout


def test_up_errors_when_weechat_missing(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    data = home / ".local" / "share" / "irclaude"
    bin_dir = data / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ergo").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "ergo").chmod(0o755)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("irclaude.cli.shutil.which", lambda name: None)

    result = runner.invoke(app, ["up"])
    assert result.exit_code == 1
    assert "weechat not on PATH" in result.stdout


def test_up_skips_spawn_when_bridge_already_running(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    data = home / ".local" / "share" / "irclaude"
    bin_dir = data / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ergo").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "ergo").chmod(0o755)
    run_dir = data / "run"
    run_dir.mkdir(parents=True)
    pid_file = run_dir / "irclaude.pid"
    pid_file.write_text("12345")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("irclaude.cli.shutil.which", lambda name: "/usr/bin/weechat")
    monkeypatch.setattr("irclaude.cli._pid_alive", lambda pid: True)

    spawn_calls: list = []
    monkeypatch.setattr(
        "irclaude.cli.subprocess.Popen",
        lambda *a, **kw: spawn_calls.append(a) or (_ for _ in ()).throw(
            AssertionError("Popen should not be called when bridge is already running")
        ),
    )
    weechat_calls: list = []

    class FakeProc:
        returncode = 0

    def fake_run(cmd, *a, **kw):
        weechat_calls.append(cmd)
        return FakeProc()

    monkeypatch.setattr("irclaude.cli.subprocess.run", fake_run)

    result = runner.invoke(app, ["up"])
    assert result.exit_code == 0
    assert "already running" in result.stdout
    assert weechat_calls == [["weechat"]]
