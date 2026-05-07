import asyncio
import contextlib
import json
import shutil
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from pathlib import Path as _Path
from typing import AsyncIterator

from irclaude.models import Project as _Project
from irclaude.services.memory_service import MemoryService as _MemoryService


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
        is_resume: bool = True,
    ) -> None:
        self.cwd = Path(cwd)
        self.claude_uuid = claude_uuid
        self.mcp_config_path = Path(mcp_config_path)
        self.digest_path = Path(digest_path)
        self.executable = Path(executable) if isinstance(executable, Path) else (
            Path(shutil.which(executable) or executable)
        )
        self.idle_timeout_s = idle_timeout_s
        self.is_resume = is_resume
        self.last_result: TurnResult | None = None

    def _argv(self, prompt: str) -> list[str]:
        session_flag = "--resume" if self.is_resume else "--session-id"
        argv = [
            str(self.executable),
            "-p",
            session_flag,
            self.claude_uuid,
            "--output-format",
            "stream-json",
            "--verbose",
            "--mcp-config",
            str(self.mcp_config_path),
            # Pre-approve the irclaude MCP tools. In `-p` mode there is no
            # interactive permission prompt, so any tool that isn't pre-allowed
            # blocks indefinitely on the permission gate.
            "--allowedTools",
            (
                "mcp__irclaude__save_decision,"
                "mcp__irclaude__save_recall,"
                "mcp__irclaude__save_summary,"
                "mcp__irclaude__recall,"
                "mcp__irclaude__list_decisions,"
                "mcp__irclaude__list_recent_sessions"
            ),
        ]
        try:
            digest_body = self.digest_path.read_text(encoding="utf-8")
        except OSError:
            digest_body = ""
        if digest_body:
            argv.extend(["--append-system-prompt", digest_body])
        argv.append(prompt)
        return argv

    async def run_turn(self, prompt: str) -> AsyncIterator[dict]:
        argv = self._argv(prompt)
        print(f"[claude] spawn argv={argv}")
        # Bump StreamReader limit so claude --verbose's giant `init` line
        # (full MCP tool list) doesn't overflow the 64 KB default.
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=8 * 1024 * 1024,
        )
        events = 0
        # Drain stderr concurrently so a chatty subprocess can't deadlock by
        # filling its 64 KB stderr pipe while we're blocked on stdout.
        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            if proc.stderr is None:
                return
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    return
                stderr_chunks.append(chunk)

        stderr_task = asyncio.create_task(_drain_stderr())
        try:
            assert proc.stdout is not None
            while True:
                try:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=self.idle_timeout_s
                    )
                except asyncio.TimeoutError:
                    print(f"[claude] idle timeout after {self.idle_timeout_s}s, terminating")
                    proc.terminate()
                    raise
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                print(f"[claude] <- {line[:4000]}")
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events += 1
                yield event
        finally:
            with contextlib.suppress(ProcessLookupError):
                if proc.returncode is None:
                    proc.terminate()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
            await proc.wait()
            self.last_result = TurnResult(
                exit_code=proc.returncode or 0,
                stderr=b"".join(stderr_chunks).decode("utf-8", errors="replace"),
            )
            print(
                f"[claude] exit={self.last_result.exit_code} events={events} "
                f"stderr={self.last_result.stderr.strip()[:300]!r}"
            )


def _claude_conversation_exists(
    claude_uuid: str,
    *,
    search_root: _Path | None = None,
) -> bool:
    root = search_root if search_root is not None else _Path.home() / ".claude" / "projects"
    if not root.exists():
        return False
    for proj_dir in root.iterdir():
        if (proj_dir / f"{claude_uuid}.jsonl").exists():
            return True
    return False


def resolve_claude_uuid(
    memory: _MemoryService,
    project: _Project,
    session_id: int,
    *,
    search_root: _Path | None = None,
) -> str:
    candidate = project.last_session_id
    if candidate and _claude_conversation_exists(candidate, search_root=search_root):
        memory.set_claude_session_id(session_id, candidate)
        return candidate
    fresh = str(_uuid.uuid4())
    memory.set_claude_session_id(session_id, fresh)
    return fresh
