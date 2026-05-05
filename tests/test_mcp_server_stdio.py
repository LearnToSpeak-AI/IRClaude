import json
import subprocess
import sys
from pathlib import Path


def test_mcp_server_responds_to_initialize(tmp_path: Path):
    """End-to-end: spawn the MCP server as subprocess, send initialize, expect response."""
    db = tmp_path / "t.db"
    from myorch.db import connect, init_schema
    from myorch.models import Project
    from myorch.services.memory_service import MemoryService
    conn = connect(db)
    init_schema(conn)
    MemoryService(conn).upsert_project(Project(name="alpha", path="/tmp/alpha"))
    conn.close()

    env = {
        "MYORCH_DB": str(db),
        "MYORCH_PROJECT": "alpha",
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path.cwd()),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "myorch.mcp_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True,
    )
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {}, "clientInfo": {"name": "test", "version": "0.1"},
        },
    }) + "\n"
    proc.stdin.write(request)
    proc.stdin.flush()
    proc.stdin.close()  # Close stdin to signal end of input
    line = proc.stdout.readline()
    proc.terminate()
    proc.wait(timeout=5)
    assert line, f"no response. stderr: {proc.stderr.read()}"
    resp = json.loads(line)
    assert resp.get("id") == 1
    assert "result" in resp
