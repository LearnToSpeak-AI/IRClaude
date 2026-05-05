import json
from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.models import Project, SessionStatus
from myorch.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> tuple[MemoryService, int]:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    assert p.id
    return m, p.id


def test_start_session_creates_active_row(memory):
    m, pid = memory
    s = m.start_session(pid)
    assert s.id is not None
    assert s.status == SessionStatus.active
    assert s.project_id == pid


def test_set_claude_session_id_persists_and_updates_project(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.set_claude_session_id(s.id, "claude-uuid-abc")  # type: ignore[arg-type]
    s2 = m.get_session(s.id)  # type: ignore[arg-type]
    assert s2.claude_session_id == "claude-uuid-abc"
    p = m.get_project_by_id(pid)
    assert p.last_session_id == "claude-uuid-abc"


def test_save_summary_writes_summary_and_files(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.save_summary(s.id, "did stuff", ["a.py", "b.py"])  # type: ignore[arg-type]
    s2 = m.get_session(s.id)  # type: ignore[arg-type]
    assert s2.summary == "did stuff"
    assert s2.files_touched == ["a.py", "b.py"]


def test_close_session_sets_status_and_ended_at(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.close_session(s.id, status=SessionStatus.closed)  # type: ignore[arg-type]
    s2 = m.get_session(s.id)  # type: ignore[arg-type]
    assert s2.status == SessionStatus.closed
    assert s2.ended_at is not None


def test_list_recent_sessions_orders_desc(memory):
    m, pid = memory
    s1 = m.start_session(pid)
    s2 = m.start_session(pid)
    out = m.list_recent_sessions(pid, limit=10)
    assert out[0].id == s2.id
    assert out[1].id == s1.id
