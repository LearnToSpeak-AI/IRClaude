from irclaude.bridge.router import ChannelRouter, project_to_channel
from irclaude.db import connect, init_schema
from irclaude.models import Project
from irclaude.services.memory_service import MemoryService


def _memory(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    return MemoryService(conn)


def test_project_to_channel_lowercases_and_strips_special_chars():
    assert project_to_channel("SpeakingMCP") == "#speakingmcp"
    assert project_to_channel("My App!!") == "#my-app"
    assert project_to_channel("ABC___DEF") == "#abc-def"


def test_project_to_channel_collapses_repeated_dashes():
    assert project_to_channel("a   b") == "#a-b"
    assert project_to_channel("a---b") == "#a-b"


def test_project_to_channel_truncates_to_50_chars():
    name = "x" * 80
    out = project_to_channel(name)
    assert len(out) <= 50
    assert out.startswith("#")


def test_project_to_channel_handles_unicode():
    assert project_to_channel("Garcon") == "#garcon"


def test_router_lists_channels_for_known_projects(tmp_path):
    mem = _memory(tmp_path)
    mem.upsert_project(Project(name="Speaking MCP", path="/p/speakingmcp"))
    mem.upsert_project(Project(name="Gate", path="/p/gate"))
    router = ChannelRouter(memory=mem)
    chans = router.channels_for_known_projects()
    assert "#speaking-mcp" in chans
    assert "#gate" in chans


def test_router_resolves_channel_back_to_project(tmp_path):
    mem = _memory(tmp_path)
    mem.upsert_project(Project(name="Speaking MCP", path="/p/sm"))
    router = ChannelRouter(memory=mem)
    proj = router.project_for_channel("#speaking-mcp")
    assert proj is not None
    assert proj.name == "Speaking MCP"


def test_router_returns_none_for_unknown_channel(tmp_path):
    mem = _memory(tmp_path)
    router = ChannelRouter(memory=mem)
    assert router.project_for_channel("#unknown") is None


def test_router_handles_collisions_with_numeric_suffix(tmp_path):
    mem = _memory(tmp_path)
    mem.upsert_project(Project(name="Foo Bar", path="/p/a"))
    mem.upsert_project(Project(name="foo-bar", path="/p/b"))
    router = ChannelRouter(memory=mem)
    chans = router.channels_for_known_projects()
    assert "#foo-bar" in chans
    assert "#foo-bar-2" in chans
