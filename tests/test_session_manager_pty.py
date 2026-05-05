import time
from pathlib import Path

import pytest

from myorch.services.session_manager import PtySession


def test_pty_writes_and_reads_with_cat():
    session = PtySession(["cat"], cwd=str(Path.home()))
    session.spawn()
    try:
        session.write("hello\n")
        deadline = time.time() + 2.0
        out = ""
        while time.time() < deadline and "hello" not in out:
            chunk = session.read_nonblocking(timeout=0.2)
            if chunk:
                out += chunk
        assert "hello" in out
    finally:
        session.terminate()


def test_pty_terminate_kills_process():
    session = PtySession(["sleep", "30"], cwd="/tmp")
    session.spawn()
    assert session.is_alive()
    session.terminate()
    deadline = time.time() + 3.0
    while session.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    assert not session.is_alive()
