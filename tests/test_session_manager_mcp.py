import json
from pathlib import Path

import pytest

from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.models import Project
from myorch.services.memory_service import MemoryService
from myorch.services.session_manager import SessionManager


def test_mcp_config_for_session_has_correct_project(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    settings = Settings()
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    proj_dir = tmp_path / "alpha"
    proj_dir.mkdir()
    p = memory.upsert_project(Project(name="alpha", path=str(proj_dir)))
    captured: dict = {}

    def fake_factory(project, digest_path, claude_uuid, is_resume, mcp_config_path):
        captured["mcp_path"] = mcp_config_path
        captured["project"] = project.name
        return ["cat"]

    mgr = SessionManager(memory=memory, settings=settings, claude_argv_factory=fake_factory)
    handle = mgr.open(project_id=p.id)
    try:
        cfg = json.loads(Path(captured["mcp_path"]).read_text())
        env = cfg["mcpServers"]["myorch-memory"]["env"]
        assert env["MYORCH_PROJECT"] == "alpha"
        assert env["MYORCH_DB"] == str(settings.db_path)
    finally:
        mgr.close(handle.session_id)
