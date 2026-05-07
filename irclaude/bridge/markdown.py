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


# Target max width for rendered tables. The chat area in a typical IRClaude
# WeeChat layout is ~110 chars after `irclaude tune-weechat`; tables wider than
# this wrap at the terminal edge and lose grid alignment.
_TABLE_TARGET_WIDTH = 110


def _column_max_widths(headers: list[str], body: list[list[str]]) -> list[int]:
    rows = [headers] + body
    widths = [0] * len(headers)
    for row in rows:
        for i, cell in enumerate(row[: len(headers)]):
            widths[i] = max(widths[i], len(cell))
    return widths


def _fit_column_widths(natural: list[int], total_target: int) -> list[int]:
    """Shrink wide columns proportionally until the table fits `total_target`.

    Each column reserves 3 chars for borders+padding. Columns narrower than 12
    chars are kept as-is; wider columns share the remaining width.
    """
    n = len(natural)
    if n == 0:
        return natural
    overhead = 3 * n + 1
    budget = max(total_target - overhead, 12 * n)
    if sum(natural) <= budget:
        return natural
    fixed_floor = 12
    fixed = [w for w in natural if w <= fixed_floor]
    flex_indices = [i for i, w in enumerate(natural) if w > fixed_floor]
    flex_budget = budget - sum(fixed)
    flex_total = sum(natural[i] for i in flex_indices) or 1
    out = list(natural)
    for i in flex_indices:
        share = max(fixed_floor, int(natural[i] * flex_budget / flex_total))
        out[i] = share
    return out


def _render_table(block: str) -> str:
    rows = [r for r in block.strip().split("\n") if r.strip()]
    if len(rows) < 2:
        return block
    headers = _split_row(rows[0])
    body = [_split_row(r) for r in rows[2:]]
    natural = _column_max_widths(headers, body)
    fitted = _fit_column_widths(natural, _TABLE_TARGET_WIDTH)
    try:
        return tabulate(
            body,
            headers=headers,
            tablefmt="rounded_grid",
            maxcolwidths=fitted,
        )
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
