from __future__ import annotations

import json
import os
import signal
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Sequence

import pexpect

from myorch.config import Settings
from myorch.digest import generate_digest
from myorch.models import SessionStatus
from myorch.services.memory_service import MemoryService


class PtySession:
    """Thin wrapper around pexpect.spawn for one PTY-managed subprocess."""

    def __init__(self, argv: Sequence[str], cwd: str, env: dict[str, str] | None = None):
        self.argv = list(argv)
        self.cwd = cwd
        self.env = env
        self._proc: pexpect.spawn | None = None

    def spawn(self) -> None:
        self._proc = pexpect.spawn(
            self.argv[0], args=self.argv[1:], cwd=self.cwd, env=self.env,
            encoding="utf-8", timeout=None, dimensions=(40, 120),
        )

    def write(self, data: str) -> None:
        if self._proc is None:
            raise RuntimeError("not spawned")
        self._proc.send(data)

    def read_nonblocking(self, timeout: float = 0.1) -> str:
        if self._proc is None:
            return ""
        try:
            return self._proc.read_nonblocking(size=4096, timeout=timeout)
        except pexpect.TIMEOUT:
            return ""
        except pexpect.EOF:
            return ""

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.isalive()

    def terminate(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill(signal.SIGTERM)
            self._proc.wait()
        except Exception:
            try:
                self._proc.kill(signal.SIGKILL)
            except Exception:
                pass


@dataclass
class SessionHandle:
    session_id: int
    project_id: int
    pty: PtySession


class SessionManager:
    """Owns the lifecycle of one PTY-backed `claude` process per project."""

    def __init__(
        self,
        memory: MemoryService,
        settings: Settings,
        claude_argv_factory=None,
    ):
        self.memory = memory
        self.settings = settings
        self._claude_argv_factory = claude_argv_factory or _default_claude_argv
        self._handles: dict[int, SessionHandle] = {}
        self._lock = Lock()

    def open(self, project_id: int) -> SessionHandle:
        with self._lock:
            project = self.memory.get_project_by_id(project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")
            myorch_dir = Path(project.path) / ".myorch"
            myorch_dir.mkdir(exist_ok=True)
            digest_path = myorch_dir / "CLAUDE.context.md"
            digest_path.write_text(generate_digest(self.memory, project_id))
            session = self.memory.start_session(project_id)

            # Decide claude session UUID: reuse last if its conversation file
            # still exists (--resume), otherwise generate new (--session-id).
            # We must check the file because `claude --resume <uuid>` exits
            # immediately with "No conversation found" if the .jsonl is gone.
            existing_uuid = project.last_session_id
            is_resume = existing_uuid is not None and _claude_conversation_exists(existing_uuid)
            claude_uuid = existing_uuid if is_resume else str(uuid.uuid4())
            self.memory.set_claude_session_id(session.id, claude_uuid)  # type: ignore[arg-type]

            run_dir = self.settings.data_dir / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / f"{project.name}.session").write_text(str(session.id))

            # write per-session mcp.json (so MYORCH_PROJECT is correct per session)
            session_mcp_path = self.settings.data_dir / "run" / f"{project.name}.mcp.json"
            session_mcp_path.write_text(json.dumps({
                "mcpServers": {
                    "myorch-memory": {
                        "command": sys.executable,
                        "args": ["-m", "myorch.mcp_server"],
                        "env": {
                            "MYORCH_DB": str(self.settings.db_path),
                            "MYORCH_PROJECT": project.name,
                        },
                    }
                }
            }, indent=2))

            argv = self._claude_argv_factory(
                project=project, digest_path=digest_path,
                claude_uuid=claude_uuid, is_resume=is_resume,
                mcp_config_path=session_mcp_path,
            )
            env = {**os.environ,
                   "MYORCH_DB": str(self.settings.db_path),
                   "MYORCH_PROJECT": project.name}
            pty = PtySession(argv=argv, cwd=project.path, env=env)
            pty.spawn()
            handle = SessionHandle(session_id=session.id, project_id=project_id, pty=pty)  # type: ignore[arg-type]
            self._handles[session.id] = handle  # type: ignore[index]
            return handle

    def close(self, session_id: int, status: SessionStatus = SessionStatus.closed) -> None:
        with self._lock:
            handle = self._handles.pop(session_id, None)
        if handle:
            handle.pty.terminate()
        self.memory.close_session(session_id, status=status)

    def get(self, session_id: int) -> SessionHandle | None:
        return self._handles.get(session_id)

    def request_summary_and_close(self, session_id: int, timeout: float = 30.0) -> None:
        """Send the Stop hook prompt and wait up to `timeout` for save_summary to land."""
        import time
        handle = self._handles.get(session_id)
        if handle is None:
            self.memory.close_session(session_id)
            return
        prompt = (
            "\n[SISTEMA: la sesión está por cerrar. Llama AHORA a la tool MCP "
            "`save_summary(summary=..., files_touched=[...])` con un resumen de máximo "
            "5 líneas de lo trabajado, archivos tocados y decisiones nuevas. "
            "Después de hacerlo, no escribas nada más.]\n"
        )
        try:
            handle.pty.write(prompt)
        except Exception:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = self.memory.get_session(session_id)
            if s and s.summary:
                break
            time.sleep(0.1)
        self.close(session_id)


def _claude_conversation_exists(claude_uuid: str) -> bool:
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return False
    return any(base.glob(f"*/{claude_uuid}.jsonl"))


def _default_claude_argv(project, digest_path: Path, claude_uuid: str,
                         is_resume: bool, mcp_config_path: Path) -> list[str]:
    argv = ["claude"]
    if is_resume:
        argv.extend(["--resume", claude_uuid])
    else:
        argv.extend(["--session-id", claude_uuid])
    argv.extend(["--mcp-config", str(mcp_config_path)])
    argv.extend(["--append-system-prompt", f"@{digest_path}"])
    return argv
