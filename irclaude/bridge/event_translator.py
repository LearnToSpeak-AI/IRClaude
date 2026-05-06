from typing import Any

from irclaude.irc.messages import Message


def _common_tags(session_id: str, turn_id: int) -> dict[str, str]:
    return {
        "+irclaude.session-id": session_id,
        "+irclaude.turn-id": str(turn_id),
    }


def _privmsg(channel: str, text: str, kind: str, extra: dict[str, str], session_id: str, turn_id: int) -> Message:
    tags = _common_tags(session_id, turn_id)
    tags["+irclaude.kind"] = kind
    tags.update(extra)
    return Message(command="PRIVMSG", params=[channel, text], tags=tags)


def classify_agent_events(events: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    starts = [e for e in events if e.get("type") == "agent_start"]
    ends = [e for e in events if e.get("type") == "agent_end"]
    normal = [e for e in events if e.get("type") not in {"agent_start", "agent_end"}]
    return starts, ends, normal


def translate(
    event: dict[str, Any],
    channel: str,
    session_id: str,
    turn_id: int,
    *,
    agent_nick: str | None = None,
) -> list[Message]:
    et = event.get("type")
    if et == "assistant":
        msg = event.get("message") or {}
        content = msg.get("content") or []
        out: list[Message] = []
        for item in content:
            it = item.get("type")
            if it == "text":
                kind = "agent-msg" if agent_nick else "text"
                extra = {"+irclaude.agent": agent_nick} if agent_nick else {}
                out.append(_privmsg(channel, item.get("text", ""), kind, extra, session_id, turn_id))
            elif it == "tool_use":
                tool = item.get("name", "?")
                summary = f">> {tool}"
                extra = {"+irclaude.tool": tool}
                if agent_nick:
                    extra["+irclaude.agent"] = agent_nick
                out.append(_privmsg(channel, summary, "tool-use", extra, session_id, turn_id))
        return out
    if et == "user":
        msg = event.get("message") or {}
        content = msg.get("content") or []
        out = []
        for item in content:
            if item.get("type") == "tool_result":
                preview = (item.get("content") or "")[:200]
                if isinstance(preview, list):
                    preview = " ".join(str(c) for c in preview)[:200]
                out.append(_privmsg(channel, str(preview), "tool-result", {}, session_id, turn_id))
        return out
    if et == "error":
        message = event.get("message", "(error)")
        return [_privmsg(channel, f"[error] {message}", "error", {}, session_id, turn_id)]
    return []
