import threading
import time
from pathlib import Path

import pytest

from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.models import Project, SessionStatus
from myorch.services.memory_service import MemoryService
from myorch.services.session_manager import SessionManager


@pytest.fixture
def manager(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    settings = Settings()
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    proj_dir = tmp_path / "alpha"
    proj_dir.mkdir()
    p = memory.upsert_project(Project(name="alpha", path=str(proj_dir)))
    mgr = SessionManager(memory=memory, settings=settings,
                         claude_argv_factory=lambda **kw: ["cat"])
    return mgr, memory, p.id


def test_request_summary_writes_prompt_to_pty_and_waits(manager, monkeypatch):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    written: list[str] = []
    monkeypatch.setattr(handle.pty, "write", lambda s: written.append(s))

    def fake_save():
        time.sleep(0.05)
        memory.save_summary(handle.session_id, "did things", ["file.py"])

    threading.Thread(target=fake_save).start()
    mgr.request_summary_and_close(handle.session_id, timeout=2.0)
    assert any("save_summary" in w for w in written)
    s = memory.get_session(handle.session_id)
    assert s.summary == "did things"
    assert s.status == SessionStatus.closed
