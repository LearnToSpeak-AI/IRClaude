"""MCP server (stdio mode) spawned by `claude` per session.

Reads MYORCH_DB and MYORCH_PROJECT from env. Exposes 6 tools:
  recall, list_recent_sessions, list_decisions, save_decision, save_recall, save_summary

The active session id is written by Session Manager to a sidecar file
(~/.myorch/run/<project>.session). save_summary reads that file at call time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from myorch.db import connect, init_schema
from myorch.models import Decision, Project, Recall, RecallHit, SessionBrief
from myorch.services.memory_service import MemoryService


@dataclass
class McpContext:
    memory: MemoryService
    project: Project
    active_session_id: int | None = None

    def _resolve_session_id(self) -> int | None:
        if self.active_session_id is not None:
            return self.active_session_id
        sidecar = Path(os.environ.get(
            "MYORCH_SESSION_FILE",
            str(Path.home() / ".myorch" / "run" / f"{self.project.name}.session"),
        ))
        if sidecar.exists():
            try:
                return int(sidecar.read_text().strip())
            except ValueError:
                return None
        return None

    def recall(self, query: str, limit: int = 10) -> list[RecallHit]:
        return self.memory.recall(self.project.id, query, limit=limit)  # type: ignore[arg-type]

    def list_recent_sessions(self, limit: int = 5) -> list[SessionBrief]:
        return self.memory.list_recent_sessions(self.project.id, limit=limit)  # type: ignore[arg-type]

    def list_decisions(self, tag: str | None = None) -> list[Decision]:
        return self.memory.list_decisions(self.project.id, tag=tag)  # type: ignore[arg-type]

    def save_decision(self, title: str, body: str, tags: list[str] | None = None) -> int:
        d = self.memory.save_decision(
            self.project.id,  # type: ignore[arg-type]
            Decision(project_id=self.project.id, title=title, body=body, tags=tags or []),  # type: ignore[arg-type]
        )
        return d.id  # type: ignore[return-value]

    def save_recall(self, text: str, tags: list[str] | None = None) -> int:
        r = self.memory.save_recall(
            self.project.id,  # type: ignore[arg-type]
            Recall(project_id=self.project.id, text=text, tags=tags or []),  # type: ignore[arg-type]
        )
        return r.id  # type: ignore[return-value]

    def save_summary(self, summary: str, files_touched: list[str] | None = None) -> None:
        sid = self._resolve_session_id()
        if sid is None:
            raise RuntimeError("No active session — cannot save summary")
        self.memory.save_summary(sid, summary, files_touched or [])


def build_context() -> McpContext:
    db_path = os.environ.get("MYORCH_DB")
    project_name = os.environ.get("MYORCH_PROJECT")
    if not db_path:
        raise RuntimeError("MYORCH_DB env var not set")
    if not project_name:
        raise RuntimeError("MYORCH_PROJECT env var not set")
    conn = connect(Path(db_path))
    init_schema(conn)
    memory = MemoryService(conn)
    project = memory.get_project_by_name(project_name)
    if project is None:
        raise RuntimeError(f"Project {project_name!r} not found in DB")
    return McpContext(memory=memory, project=project)


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    ctx = build_context()
    mcp = FastMCP("myorch-memory")

    @mcp.tool()
    def recall(query: str, limit: int = 10) -> list[dict]:
        """Búsqueda full-text sobre memoria del proyecto activo."""
        return [h.model_dump() for h in ctx.recall(query, limit=limit)]

    @mcp.tool()
    def list_recent_sessions(limit: int = 5) -> list[dict]:
        """Las últimas N sesiones del proyecto activo con su resumen."""
        return [s.model_dump() for s in ctx.list_recent_sessions(limit=limit)]

    @mcp.tool()
    def list_decisions(tag: str | None = None) -> list[dict]:
        """Decisiones del proyecto activo, opcionalmente filtradas por tag."""
        return [d.model_dump() for d in ctx.list_decisions(tag=tag)]

    @mcp.tool()
    def save_decision(title: str, body: str, tags: list[str] | None = None) -> int:
        """Registra una decisión razonada. Devuelve el ID de la decisión."""
        return ctx.save_decision(title=title, body=body, tags=tags)

    @mcp.tool()
    def save_recall(text: str, tags: list[str] | None = None) -> int:
        """Nota rápida ('no olvides X'). Devuelve el ID."""
        return ctx.save_recall(text=text, tags=tags)

    @mcp.tool()
    def save_summary(summary: str, files_touched: list[str] | None = None) -> str:
        """Guarda el resumen de la sesión activa. Llamado por el hook Stop."""
        ctx.save_summary(summary=summary, files_touched=files_touched)
        return "ok"

    mcp.run()


if __name__ == "__main__":
    main()
