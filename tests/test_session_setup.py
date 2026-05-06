import json

from myorch.bridge.session_setup import SessionContext, prepare_session
from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.models import Project, Recall
from myorch.services.memory_service import MemoryService


def _settings(tmp_path):
    s = Settings(
        apps_root=tmp_path / "apps",
        data_dir=tmp_path / "data",
        config_file=tmp_path / "cfg.toml",
        host="127.0.0.1",
        port=6667,
    )
    s.run_dir.mkdir(parents=True, exist_ok=True)
    return s


def test_prepare_session_writes_digest_under_project(tmp_path):
    proj_path = tmp_path / "apps" / "foo"
    proj_path.mkdir(parents=True)
    settings = _settings(tmp_path)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    proj = mem.upsert_project(Project(name="Foo", path=str(proj_path)))
    mem.save_recall(proj.id, Recall(project_id=proj.id, text="key fact", tags=[]))

    ctx = prepare_session(project=proj, memory=mem, settings=settings)
    assert isinstance(ctx, SessionContext)

    digest_path = proj_path / ".myorch" / "CLAUDE.context.md"
    assert digest_path.exists()
    body = digest_path.read_text(encoding="utf-8")
    assert "key fact" in body or "Foo" in body


def test_prepare_session_writes_per_project_mcp_json(tmp_path):
    proj_path = tmp_path / "apps" / "bar"
    proj_path.mkdir(parents=True)
    settings = _settings(tmp_path)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    proj = mem.upsert_project(Project(name="Bar", path=str(proj_path)))

    ctx = prepare_session(project=proj, memory=mem, settings=settings)
    mcp_path = settings.run_dir / "Bar.mcp.json"
    assert mcp_path.exists()
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "myorch" in data["mcpServers"]
    server = data["mcpServers"]["myorch"]
    assert server["command"]
    assert "MYORCH_DATA_DIR" in server.get("env", {})
    assert server["env"]["MYORCH_PROJECT_ID"] == str(proj.id)


def test_prepare_session_returns_paths_in_context(tmp_path):
    proj_path = tmp_path / "apps" / "baz"
    proj_path.mkdir(parents=True)
    settings = _settings(tmp_path)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    proj = mem.upsert_project(Project(name="Baz", path=str(proj_path)))

    ctx = prepare_session(project=proj, memory=mem, settings=settings)
    assert ctx.digest_path.is_file()
    assert ctx.mcp_config_path.is_file()
    assert ctx.session_id > 0
    assert len(ctx.claude_uuid) >= 8
