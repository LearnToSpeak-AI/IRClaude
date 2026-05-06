from pathlib import Path

from irclaude.bridge.claude_runner import (
    _claude_conversation_exists,
    resolve_claude_uuid,
)
from irclaude.db import connect, init_schema
from irclaude.models import Project
from irclaude.services.memory_service import MemoryService


def _memory(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    return MemoryService(conn)


def test_claude_conversation_exists_finds_jsonl(tmp_path: Path):
    proj_dir = tmp_path / ".claude" / "projects" / "encoded"
    proj_dir.mkdir(parents=True)
    (proj_dir / "abc-123.jsonl").write_text("{}\n", encoding="utf-8")
    assert _claude_conversation_exists("abc-123", search_root=tmp_path / ".claude" / "projects") is True


def test_claude_conversation_exists_returns_false_when_missing(tmp_path: Path):
    assert _claude_conversation_exists("nope", search_root=tmp_path) is False


def test_resolve_claude_uuid_reuses_existing(tmp_path: Path):
    mem = _memory(tmp_path)
    proj = mem.upsert_project(Project(name="P", path=str(tmp_path), last_session_id=None))
    proj = mem.update_project(proj.id, last_session_id="known-uuid")
    sess = mem.start_session(proj.id)

    proj_dir = tmp_path / ".claude" / "projects" / "p"
    proj_dir.mkdir(parents=True)
    (proj_dir / "known-uuid.jsonl").write_text("{}", encoding="utf-8")

    out = resolve_claude_uuid(
        memory=mem,
        project=proj,
        session_id=sess.id,
        search_root=tmp_path / ".claude" / "projects",
    )
    assert out == "known-uuid"


def test_resolve_claude_uuid_generates_fresh_when_jsonl_missing(tmp_path: Path):
    mem = _memory(tmp_path)
    proj = mem.upsert_project(Project(name="P", path=str(tmp_path), last_session_id="ghost"))
    proj = mem.get_project_by_id(proj.id)
    sess = mem.start_session(proj.id)

    out = resolve_claude_uuid(
        memory=mem,
        project=proj,
        session_id=sess.id,
        search_root=tmp_path / ".claude" / "projects",
    )
    assert out != "ghost"
    refreshed = mem.get_session(sess.id)
    assert refreshed.claude_session_id == out
