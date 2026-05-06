import asyncio
import contextlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator


@dataclass
class TurnResult:
    exit_code: int
    stderr: str


class ClaudeRunner:
    def __init__(
        self,
        cwd: Path,
        claude_uuid: str,
        mcp_config_path: Path,
        digest_path: Path,
        *,
        executable: Path | str = "claude",
        idle_timeout_s: float = 30.0,
    ) -> None:
        self.cwd = Path(cwd)
        self.claude_uuid = claude_uuid
        self.mcp_config_path = Path(mcp_config_path)
        self.digest_path = Path(digest_path)
        self.executable = Path(executable) if isinstance(executable, Path) else (
            Path(shutil.which(executable) or executable)
        )
        self.idle_timeout_s = idle_timeout_s
        self.last_result: TurnResult | None = None

    def _argv(self, prompt: str) -> list[str]:
        return [
            str(self.executable),
            "-p",
            "--resume",
            self.claude_uuid,
            "--output-format",
            "stream-json",
            "--append-system-prompt",
            f"@{self.digest_path}",
            "--mcp-config",
            str(self.mcp_config_path),
            prompt,
        ]

    async def run_turn(self, prompt: str) -> AsyncIterator[dict]:
        argv = self._argv(prompt)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert proc.stdout is not None
            while True:
                try:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=self.idle_timeout_s
                    )
                except asyncio.TimeoutError:
                    proc.terminate()
                    raise
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        finally:
            with contextlib.suppress(ProcessLookupError):
                if proc.returncode is None:
                    proc.terminate()
            stderr_b = await proc.stderr.read() if proc.stderr is not None else b""
            await proc.wait()
            self.last_result = TurnResult(
                exit_code=proc.returncode or 0,
                stderr=stderr_b.decode("utf-8", errors="replace"),
            )
