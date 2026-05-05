import time
from pathlib import Path

from myorch.services.dev_server_manager import DevServerManager


def test_start_runs_command_and_captures_output(tmp_path: Path):
    mgr = DevServerManager()
    mgr.start(project_id=1, command="echo hello && sleep 1", cwd=str(tmp_path))
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if any("hello" in line for line in mgr.tail(1)):
            break
        time.sleep(0.05)
    assert any("hello" in line for line in mgr.tail(1))
    mgr.stop(1)


def test_stop_kills_running_process(tmp_path: Path):
    mgr = DevServerManager()
    mgr.start(project_id=2, command="sleep 30", cwd=str(tmp_path))
    assert mgr.is_running(2)
    mgr.stop(2)
    deadline = time.time() + 5.0
    while mgr.is_running(2) and time.time() < deadline:
        time.sleep(0.05)
    assert not mgr.is_running(2)


def test_double_start_replaces_previous(tmp_path: Path):
    mgr = DevServerManager()
    mgr.start(project_id=3, command="sleep 30", cwd=str(tmp_path))
    pid_a = mgr._procs[3].popen.pid
    mgr.start(project_id=3, command="sleep 30", cwd=str(tmp_path))
    pid_b = mgr._procs[3].popen.pid
    assert pid_a != pid_b
    mgr.stop(3)
