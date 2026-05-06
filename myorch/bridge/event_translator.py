from typing import Any

from myorch.irc.messages import Message


def _common_tags(session_id: str, turn_id: int) -> dict[str, str]:
    return {
        "+myorch.session-id": session_id,
        "+myorch.turn-id": str(turn_id),
    }


def _privmsg(channel: str, text: str, kind: str, extra: dict[str, str], session_id: str, turn_id: int) -> Message:
    tags = _common_tags(session_id, turn_id)
    tags["+myorch.kind"] = kind
    tags.update(extra)
    return Message(command="PRIVMSG", params=[channel, text], tags=tags)


def translate(event: dict[str, Any], channel: str, session_id: str, turn_id: int) -> list[Message]:
    et = event.get("type")
    if et == "assistant":
        msg = event.get("message") or {}
        content = msg.get("content") or []
        out: list[Message] = []
        for item in content:
            it = item.get("type")
            if it == "text":
                out.append(_privmsg(channel, item.get("text", ""), "text", {}, session_id, turn_id))
            elif it == "tool_use":
                tool = item.get("name", "?")
                summary = f">> {tool}"
                out.append(_privmsg(channel, summary, "tool-use", {"+myorch.tool": tool}, session_id, turn_id))
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
