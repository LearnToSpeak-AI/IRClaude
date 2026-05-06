import json
from pathlib import Path

from irclaude.bootstrap import ensure_mcp_config
from irclaude.config import Settings


def test_writes_mcp_config_pointing_at_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IRCLAUDE_DATA_DIR", str(tmp_path / ".irclaude"))
    s = Settings()
    ensure_mcp_config(s)
    cfg = json.loads(s.mcp_config_path.read_text())
    server = cfg["mcpServers"]["irclaude-memory"]
    assert "irclaude.mcp_server" in server["args"]
    assert server["env"]["IRCLAUDE_DB"] == str(s.db_path)


def test_does_not_overwrite_existing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IRCLAUDE_DATA_DIR", str(tmp_path / ".irclaude"))
    s = Settings()
    s.mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
    s.mcp_config_path.write_text('{"customized": true}')
    ensure_mcp_config(s)
    assert s.mcp_config_path.read_text() == '{"customized": true}'
