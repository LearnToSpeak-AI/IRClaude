from irclaude.services.memory_service import MemoryService

MAX_DECISIONS = 5
MAX_RECALLS = 5


def generate_digest(memory: MemoryService, project_id: int) -> str:
    project = memory.get_project_by_id(project_id)
    if project is None:
        return "[Sin proyecto]"

    sessions = memory.list_recent_sessions(project_id, limit=1)
    decisions = memory.list_decisions(project_id)[:MAX_DECISIONS]
    recalls = memory.list_recalls(project_id)[:MAX_RECALLS]

    if not sessions and not decisions and not recalls:
        return (
            f"[Contexto del proyecto: {project.name}]\n"
            f"Sin historial todavía. La memoria crecerá conforme trabajes."
        )

    lines = [f"[Contexto del proyecto: {project.name}]"]

    if sessions and sessions[0].summary:
        lines.append("")
        lines.append(f"Última sesión ({sessions[0].started_at}):")
        lines.append(f"  {sessions[0].summary}")

    if decisions:
        lines.append("")
        lines.append(f"Decisiones activas ({len(decisions)}):")
        for d in decisions:
            lines.append(f"  • {d.title}")

    if recalls:
        lines.append("")
        lines.append(f"Recalls ({len(recalls)}):")
        for r in recalls:
            text = r.text if len(r.text) <= 120 else r.text[:117] + "..."
            lines.append(f"  • {text}")

    lines.append("")
    lines.append("Para más contexto, usa la herramienta MCP `recall(query)`.")
    return "\n".join(lines)
