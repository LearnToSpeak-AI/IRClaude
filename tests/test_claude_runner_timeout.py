import asyncio
import stat
from pathlib import Path

import pytest

from myorch.bridge.claude_runner import ClaudeRunner


def _make_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.mark.asyncio
async def test_run_turn_times_out_when_no_events_arrive(tmp_path):
    fake = _make_executable(
        tmp_path / "claude",
        "#!/usr/bin/env bash\nsleep 60\n",
    )
    digest = tmp_path / "d.md"; digest.write_text("d", encoding="utf-8")
    mcp = tmp_path / "m.json"; mcp.write_text("{}", encoding="utf-8")

    runner = ClaudeRunner(
        cwd=tmp_path,
        claude_uuid="x",
        mcp_config_path=mcp,
        digest_path=digest,
        executable=fake,
        idle_timeout_s=0.5,
    )
    with pytest.raises(asyncio.TimeoutError):
        async for _ in runner.run_turn("p"):
            pass


@pytest.mark.asyncio
async def test_run_turn_captures_stderr_when_exit_nonzero(tmp_path):
    fake = _make_executable(
        tmp_path / "claude",
        "#!/usr/bin/env bash\necho boom 1>&2\nexit 7\n",
    )
    digest = tmp_path / "d.md"; digest.write_text("d", encoding="utf-8")
    mcp = tmp_path / "m.json"; mcp.write_text("{}", encoding="utf-8")

    runner = ClaudeRunner(
        cwd=tmp_path, claude_uuid="x", mcp_config_path=mcp,
        digest_path=digest, executable=fake, idle_timeout_s=2.0,
    )
    async for _ in runner.run_turn("p"):
        pass
    assert runner.last_result is not None
    assert runner.last_result.exit_code == 7
    assert "boom" in runner.last_result.stderr
