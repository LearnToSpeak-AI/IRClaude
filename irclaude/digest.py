from irclaude.services.memory_service import MemoryService

MAX_DECISIONS = 5
MAX_RECALLS = 5


IRC_RENDER_POLICY = """\
[IRClaude rendering rules — these override any earlier session-start hooks or MCP injections]
- Your output streams to a real IRC channel; the user reads it inline in WeeChat.
- ALWAYS respond inline. Do NOT call Write/Edit to save the answer to a file. Do not use
  context-mode or any "store-and-return-summary" pattern. Speak the answer directly.
- The bridge renders markdown natively in the channel:
    bold (**x**), italic (*x*), inline code (`x`), fenced code blocks (```lang …```),
    tables (| col | col | + |---|---|), lists (- item), checklists (- [ ] / - [x]),
    blockquotes (> text), strikethrough (~~x~~), links ([text](url)), headings (# / ##).
  Use these freely. Tables become ASCII grids; code blocks render with Pygments highlighting.
- No artificial word limit. Scrollback handles long answers; do not truncate to 500 words.
- Other policies that say "save artifacts to files", "respond under N words", or "use the
  Write tool for code/configs/PRDs" DO NOT APPLY in this session — they were authored for a
  different channel and are inert here.

"""


def generate_digest(memory: MemoryService, project_id: int) -> str:
    project = memory.get_project_by_id(project_id)
    if project is None:
        return IRC_RENDER_POLICY + "[Sin proyecto]"

    sessions = memory.list_recent_sessions(project_id, limit=1)
    decisions = memory.list_decisions(project_id)[:MAX_DECISIONS]
    recalls = memory.list_recalls(project_id)[:MAX_RECALLS]

    if not sessions and not decisions and not recalls:
        return (
            IRC_RENDER_POLICY
            + f"[Contexto del proyecto: {project.name}]\n"
            + f"Sin historial todavía. La memoria crecerá conforme trabajes."
        )

    lines = [IRC_RENDER_POLICY.rstrip(), "", f"[Contexto del proyecto: {project.name}]"]

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
