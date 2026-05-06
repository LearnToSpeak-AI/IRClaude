from pathlib import Path

import pytest

from irclaude.db import connect, init_schema
from irclaude.models import Decision, Project, Recall
from irclaude.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> tuple[MemoryService, int]:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    return m, p.id  # type: ignore[return-value]


def test_save_decision_returns_id(memory):
    m, pid = memory
    d = m.save_decision(pid, Decision(project_id=pid, title="JWT", body="auth"))
    assert d.id is not None


def test_list_decisions_filters_by_tag(memory):
    m, pid = memory
    m.save_decision(pid, Decision(project_id=pid, title="A", body="x", tags=["auth"]))
    m.save_decision(pid, Decision(project_id=pid, title="B", body="y", tags=["db"]))
    auth = m.list_decisions(pid, tag="auth")
    assert len(auth) == 1 and auth[0].title == "A"
    all_ = m.list_decisions(pid, tag=None)
    assert len(all_) == 2


def test_save_recall_persists(memory):
    m, pid = memory
    r = m.save_recall(pid, Recall(project_id=pid, text="X-Forwarded-For required"))
    assert r.id is not None


def test_recall_search_finds_decisions_recalls_and_summaries(memory):
    m, pid = memory
    m.save_decision(pid, Decision(project_id=pid, title="JWT", body="auth via simplejwt"))
    m.save_recall(pid, Recall(project_id=pid, text="endpoint X needs JWT"))
    s = m.start_session(pid)
    m.save_summary(s.id, "Implemented JWT login")  # type: ignore[arg-type]
    hits = m.recall(pid, "JWT", limit=10)
    origins = {h.origin for h in hits}
    assert "decision:1" in origins
    assert "recall:1" in origins
    assert "session:1" in origins


def test_recall_does_not_leak_other_projects(memory):
    m, pid = memory
    p2 = m.upsert_project(Project(name="beta", path="/tmp/beta"))
    m.save_decision(pid, Decision(project_id=pid, title="JWT alpha", body="alpha-only"))
    m.save_decision(p2.id, Decision(project_id=p2.id, title="JWT beta", body="beta-only"))  # type: ignore[arg-type]
    hits = m.recall(pid, "JWT")
    assert len(hits) == 1
    assert "alpha-only" in hits[0].snippet or "JWT alpha" in hits[0].snippet
