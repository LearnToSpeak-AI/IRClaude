import re

from tabulate import tabulate


_BOLD = re.compile(r"\*\*(.+?)\*\*", flags=re.DOTALL)
_STRIKE = re.compile(r"~~(.+?)~~", flags=re.DOTALL)
_ITAL = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", flags=re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CHECK_DONE = re.compile(r"^- \[[xX]\] ", flags=re.MULTILINE)
_CHECK_TODO = re.compile(r"^- \[ \] ", flags=re.MULTILINE)
_LIST = re.compile(r"^- ", flags=re.MULTILINE)
_H1 = re.compile(r"^# (.+)$", flags=re.MULTILINE)
_H2 = re.compile(r"^## (.+)$", flags=re.MULTILINE)
_QUOTE = re.compile(r"^> (.+)$", flags=re.MULTILINE)
# Markdown table: header row, separator row of dashes/colons, ≥1 data rows.
_TABLE = re.compile(
    r"(^\|[^\n]+\|[ \t]*\n"           # header row
    r"\|[\s:|\-]+\|[ \t]*\n"          # separator row of dashes/colons
    r"(?:\|[^\n]+\|[ \t]*\n?)+)",     # one or more data rows
    flags=re.MULTILINE,
)


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _render_table(block: str) -> str:
    rows = [r for r in block.strip().split("\n") if r.strip()]
    if len(rows) < 2:
        return block
    headers = _split_row(rows[0])
    body = [_split_row(r) for r in rows[2:]]
    try:
        return tabulate(body, headers=headers, tablefmt="rounded_grid")
    except Exception:
        return block


def markdown_to_irc(text: str) -> str:
    """Map a small subset of markdown to IRC formatting codes."""
    out = text
    # Tables first — their pipe characters would otherwise interact with later
    # regexes (links, etc.).
    out = _TABLE.sub(lambda m: _render_table(m.group(1)), out)
    out = _H1.sub(lambda m: f"\x0307\x02{m.group(1)}\x02\x0F", out)
    out = _H2.sub(lambda m: f"\x0306\x02{m.group(1)}\x02\x0F", out)
    # Checklists must replace before the bare-list rule ('- ') consumes the dash.
    out = _CHECK_DONE.sub("\x0303☑\x0F ", out)
    out = _CHECK_TODO.sub("☐ ", out)
    out = _BOLD.sub(lambda m: f"\x02{m.group(1)}\x02", out)
    out = _STRIKE.sub(lambda m: f"\x1E{m.group(1)}\x1E", out)
    out = _ITAL.sub(lambda m: f"\x1D{m.group(1)}\x1D", out)
    # Inline code: light-grey (\x0314) instead of \x11 (monospace) — not all
    # terminals render \x11 and many display it as a stray caret/control char.
    out = _INLINE_CODE.sub(lambda m: f"\x0314{m.group(1)}\x0F", out)
    out = _LINK.sub(lambda m: f"\x1F{m.group(1)}\x1F ({m.group(2)})", out)
    out = _QUOTE.sub(lambda m: f"\x0314▌\x0F {m.group(1)}", out)
    out = _LIST.sub("· ", out)
    return out
