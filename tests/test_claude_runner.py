import stat
from pathlib import Path

import pytest

from irclaude.bridge.claude_runner import ClaudeRunner


@pytest.fixture
def fake_claude(tmp_path: Path) -> Path:
    src = Path(__file__).parent / "fixtures" / "fake_claude.sh"
    dst = tmp_path / "claude"
    dst.write_bytes(src.read_bytes())
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return dst


@pytest.mark.asyncio
async def test_run_turn_streams_canned_events(tmp_path, fake_claude):
    digest = tmp_path / "digest.md"
    digest.write_text("hello", encoding="utf-8")
    mcp = tmp_path / "mcp.json"
    mcp.write_text("{}", encoding="utf-8")

    runner = ClaudeRunner(
        cwd=tmp_path,
        claude_uuid="11111111-2222-3333-4444-555555555555",
        mcp_config_path=mcp,
        digest_path=digest,
        executable=fake_claude,
    )
    events = []
    async for event in runner.run_turn("hi there"):
        events.append(event)

    types = [e["type"] for e in events]
    assert types == ["system", "assistant", "result"]
    assert events[1]["message"]["content"][0]["text"] == "hi"


@pytest.mark.asyncio
async def test_run_turn_includes_required_flags(tmp_path):
    fake = tmp_path / "claude_log.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" > \"$0.argv\"\n"
        "echo '{\"type\":\"result\",\"subtype\":\"success\"}'\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    digest = tmp_path / "digest.md"; digest.write_text("d", encoding="utf-8")
    mcp = tmp_path / "mcp.json"; mcp.write_text("{}", encoding="utf-8")

    runner = ClaudeRunner(
        cwd=tmp_path, claude_uuid="abc", mcp_config_path=mcp,
        digest_path=digest, executable=fake,
    )
    async for _ in runner.run_turn("hello"):
        pass

    argv = (tmp_path / "claude_log.sh.argv").read_text(encoding="utf-8").splitlines()
    assert "-p" in argv
    assert "--resume" in argv
    assert "abc" in argv
    assert "--output-format" in argv
    assert "stream-json" in argv
    assert "--mcp-config" in argv
    assert str(mcp) in argv
    assert any("digest.md" in a for a in argv)
    assert "hello" in argv
