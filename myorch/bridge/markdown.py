import re


_BOLD = re.compile(r"\*\*(.+?)\*\*", flags=re.DOTALL)
_ITAL = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", flags=re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LIST = re.compile(r"^- ", flags=re.MULTILINE)
_H1 = re.compile(r"^# (.+)$", flags=re.MULTILINE)
_H2 = re.compile(r"^## (.+)$", flags=re.MULTILINE)


def markdown_to_irc(text: str) -> str:
    """Map a small subset of markdown to IRC formatting codes."""
    out = text
    out = _H1.sub(lambda m: f"\x0307\x02{m.group(1)}\x02\x0F", out)
    out = _H2.sub(lambda m: f"\x0306\x02{m.group(1)}\x02\x0F", out)
    out = _BOLD.sub(lambda m: f"\x02{m.group(1)}\x02", out)
    out = _ITAL.sub(lambda m: f"\x1D{m.group(1)}\x1D", out)
    out = _INLINE_CODE.sub(lambda m: f"\x11{m.group(1)}\x11", out)
    out = _LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", out)
    out = _LIST.sub("· ", out)
    return out
