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
    monkeypatch.setenv("MYORCH_TMP_DIR", str(tmp_path / "tmp"))
    settings = Settings()
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    proj_dir = tmp_path / "alpha"
    proj_dir.mkdir()
    p = memory.upsert_project(Project(name="alpha", path=str(proj_dir)))
    mgr = SessionManager(memory=memory, settings=settings,
                         claude_argv_factory=lambda **kw: ["cat"])
    return mgr, memory, p.id  # type: ignore[return-value]


def test_open_session_creates_active_db_row_and_sidecar(manager):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    try:
        s = memory.get_session(handle.session_id)
        assert s.status == SessionStatus.active
        sidecar = mgr.settings.data_dir / "run" / "alpha.session"
        assert sidecar.exists()
        assert sidecar.read_text().strip() == str(handle.session_id)
    finally:
        mgr.close(handle.session_id)


def test_close_session_terminates_and_marks_closed(manager):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    mgr.close(handle.session_id)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        s = memory.get_session(handle.session_id)
        if s.status == SessionStatus.closed:
            return
        time.sleep(0.05)
    pytest.fail("session not marked closed in time")


def test_open_writes_digest_file(manager):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    try:
        digest_path = Path(memory.get_project_by_id(pid).path) / ".myorch" / "CLAUDE.context.md"
        assert digest_path.exists()
        assert "alpha" in digest_path.read_text()
    finally:
        mgr.close(handle.session_id)


def test_open_persists_uuid_session_id_to_project(manager):
    """New addition: confirm we generate and persist a UUID via set_claude_session_id."""
    import uuid as uuid_mod
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    try:
        p = memory.get_project_by_id(pid)
        assert p.last_session_id is not None
        # verify it's a valid UUID
        uuid_mod.UUID(p.last_session_id)
    finally:
        mgr.close(handle.session_id)
