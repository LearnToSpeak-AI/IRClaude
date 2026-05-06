from pathlib import Path

import pytest

from irclaude.db import connect, init_schema
from irclaude.digest import generate_digest
from irclaude.models import Decision, Project, Recall
from irclaude.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> tuple[MemoryService, int]:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="gate", path="/tmp/gate"))
    return m, p.id  # type: ignore[return-value]


def test_digest_for_empty_project_says_no_history(memory):
    m, pid = memory
    text = generate_digest(m, pid)
    assert "Sin historial" in text or "no history" in text.lower()


def test_digest_includes_last_session_summary(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.save_summary(s.id, "Implemented refresh tokens", ["auth.py"])  # type: ignore[arg-type]
    text = generate_digest(m, pid)
    assert "refresh tokens" in text


def test_digest_includes_decisions_and_recalls(memory):
    m, pid = memory
    m.save_decision(pid, Decision(project_id=pid, title="JWT auth", body="via simplejwt"))
    m.save_recall(pid, Recall(project_id=pid, text="endpoint X needs token"))
    text = generate_digest(m, pid)
    assert "JWT auth" in text
    assert "endpoint X needs token" in text


def test_digest_under_token_budget(memory):
    m, pid = memory
    for i in range(50):
        m.save_decision(pid, Decision(project_id=pid, title=f"D{i}", body="x" * 200))
    text = generate_digest(m, pid)
    # rough heuristic: keep under ~600 tokens ~= 2400 chars
    assert len(text) < 4000
