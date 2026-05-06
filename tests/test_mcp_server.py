import os
from pathlib import Path

import pytest

from irclaude.db import connect, init_schema
from irclaude.mcp_server import McpContext, build_context
from irclaude.models import Decision, Project, Recall
from irclaude.services.memory_service import MemoryService


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch) -> McpContext:
    db = tmp_path / "t.db"
    conn = connect(db)
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    monkeypatch.setenv("IRCLAUDE_DB", str(db))
    monkeypatch.setenv("IRCLAUDE_PROJECT", "alpha")
    return build_context()


def test_build_context_resolves_project_from_env(ctx: McpContext):
    assert ctx.project.name == "alpha"


def test_build_context_raises_when_env_missing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("IRCLAUDE_PROJECT", raising=False)
    monkeypatch.setenv("IRCLAUDE_DB", str(tmp_path / "t.db"))
    with pytest.raises(RuntimeError, match="IRCLAUDE_PROJECT"):
        build_context()


def test_recall_tool_returns_hits(ctx: McpContext):
    ctx.memory.save_decision(
        ctx.project.id,
        Decision(project_id=ctx.project.id, title="JWT", body="use simplejwt"),
    )
    hits = ctx.recall("JWT", limit=5)
    assert len(hits) == 1


def test_save_decision_tool_persists(ctx: McpContext):
    new_id = ctx.save_decision(title="Postgres", body="not sqlite", tags=["db"])
    assert new_id > 0
    decisions = ctx.memory.list_decisions(ctx.project.id)
    assert any(d.title == "Postgres" for d in decisions)


def test_save_recall_tool_persists(ctx: McpContext):
    new_id = ctx.save_recall(text="port 8000", tags=["dev"])
    assert new_id > 0
    recalls = ctx.memory.list_recalls(ctx.project.id)
    assert any(r.text == "port 8000" for r in recalls)


def test_save_summary_writes_to_active_session(ctx: McpContext):
    s = ctx.memory.start_session(ctx.project.id)
    ctx.active_session_id = s.id
    ctx.save_summary(summary="did stuff", files_touched=["a.py"])
    s2 = ctx.memory.get_session(s.id)
    assert s2.summary == "did stuff"
    assert s2.files_touched == ["a.py"]


def test_list_recent_sessions_tool(ctx: McpContext):
    ctx.memory.start_session(ctx.project.id)
    out = ctx.list_recent_sessions(limit=5)
    assert len(out) == 1


def test_list_decisions_tool_filters_by_tag(ctx: McpContext):
    ctx.save_decision(title="A", body="x", tags=["auth"])
    ctx.save_decision(title="B", body="y", tags=["db"])
    only_auth = ctx.list_decisions(tag="auth")
    assert len(only_auth) == 1
    assert only_auth[0].title == "A"
