import os
import signal

from typer.testing import CliRunner

from myorch.cli import app


runner = CliRunner()


def test_status_shows_not_running_when_no_pid_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / "d"))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not running" in result.stdout.lower()


def test_status_shows_running_when_pid_alive(monkeypatch, tmp_path):
    data = tmp_path / "d"; (data / "run").mkdir(parents=True)
    (data / "run" / "myorch.pid").write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch.setenv("MYORCH_DATA_DIR", str(data))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "running" in result.stdout.lower()
    assert str(os.getpid()) in result.stdout


def test_stop_signals_pid_and_removes_file(monkeypatch, tmp_path):
    data = tmp_path / "d"; (data / "run").mkdir(parents=True)
    pid_file = data / "run" / "myorch.pid"
    sent: list[tuple[int, int]] = []

    def fake_kill(pid, sig):
        sent.append((pid, sig))

    monkeypatch.setattr("myorch.cli.os.kill", fake_kill, raising=False)
    pid_file.write_text("12345", encoding="utf-8")
    monkeypatch.setenv("MYORCH_DATA_DIR", str(data))
    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert sent and sent[0] == (12345, signal.SIGTERM)
    assert not pid_file.exists()


def test_start_writes_pid_file(monkeypatch, tmp_path):
    data = tmp_path / "d"; data.mkdir()
    monkeypatch.setenv("MYORCH_DATA_DIR", str(data))
    monkeypatch.setattr(
        "myorch.cli._launch_bridge_blocking", lambda settings: None, raising=False
    )
    result = runner.invoke(app, ["start"])
    assert result.exit_code == 0
    pid_file = data / "run" / "myorch.pid"
    assert pid_file.exists()
    assert pid_file.read_text(encoding="utf-8").strip().isdigit()
