import re

from pygments import highlight
from pygments.formatters import IRCFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from irclaude.bridge.markdown import markdown_to_irc
from irclaude.irc.messages import Message
from irclaude.irc.protocol import encode_batch, encode_multiline, new_batch_id


_FENCE = re.compile(r"^```(\S*)\s*$")
_BORDER_COLOR = "\x0314"  # light grey
_RESET = "\x0F"


def _highlight_code_lines(lang: str, lines: list[str]) -> list[str]:
    """Apply Pygments IRC-color highlighting to code lines.

    Falls back to the raw lines if the language is unknown or Pygments errors out.
    """
    text = "\n".join(lines)
    try:
        lexer = get_lexer_by_name(lang, stripnl=False)
    except ClassNotFound:
        return list(lines)
    try:
        formatted = highlight(text, lexer, IRCFormatter())
    except Exception:
        return list(lines)
    out = formatted.split("\n")
    if out and out[-1] == "":
        out.pop()
    return out


class CodeBlockBuffer:
    """Stateful buffer for streamed text to tagged IRC lines.

    Detects fenced code blocks across feed() calls and emits BATCH +irclaude.codeblock=<lang>
    sequences for them, while plain text passes through (multiline becomes a draft/multiline batch).
    """

    def __init__(self, channel: str, session_id: str, turn_id: int) -> None:
        self.channel = channel
        self.session_id = session_id
        self.turn_id = turn_id
        self._pending = ""
        self._in_code = False
        self._code_lang = "text"
        self._code_lines: list[str] = []
        self._text_buffer = ""

    def _common_tags(self) -> dict[str, str]:
        return {
            "+irclaude.session-id": self.session_id,
            "+irclaude.turn-id": str(self.turn_id),
        }

    def _emit_text_block(self, text: str) -> list[str]:
        if not text:
            return []
        tags = self._common_tags()
        tags["+irclaude.kind"] = "text"
        # WeeChat 4.1's draft/multiline support doesn't surface assembled
        # batches to the print pipeline, so the BATCH'd content disappears.
        # Emit one PRIVMSG per line — each row renders independently with the
        # `<claude>` prefix repeated.
        rendered = markdown_to_irc(text)
        return [
            Message(
                command="PRIVMSG",
                params=[self.channel, line or " "],
                tags=dict(tags),
            ).encode()
            for line in rendered.split("\n")
        ]

    def _emit_code_block(self, lang: str, lines: list[str]) -> list[str]:
        if not lines:
            return []
        tags = self._common_tags()
        tags["+irclaude.kind"] = "code"
        tags["+irclaude.lang"] = lang
        body = [
            f"{_BORDER_COLOR}─── {lang} ───{_RESET}",
            *_highlight_code_lines(lang, lines),
            f"{_BORDER_COLOR}───{_RESET}",
        ]
        return encode_batch(
            batch_id=new_batch_id(),
            type_="draft/multiline",
            tags=tags,
            target=self.channel,
            contents=body,
        )

    def feed(self, chunk: str) -> list[str]:
        self._pending += chunk
        out: list[str] = []
        if "\n" in self._pending:
            lines, _, rest = self._pending.rpartition("\n")
            self._pending = rest
            for line in lines.split("\n"):
                out.extend(self._consume_line(line))
        return out

    def _consume_line(self, line: str) -> list[str]:
        m = _FENCE.match(line)
        if m:
            if not self._in_code:
                txt_out = self._flush_text_buffer()
                self._in_code = True
                self._code_lang = m.group(1) or "text"
                self._code_lines = []
                return txt_out
            out = self._emit_code_block(self._code_lang, self._code_lines)
            self._in_code = False
            self._code_lang = "text"
            self._code_lines = []
            return out

        if self._in_code:
            self._code_lines.append(line)
            return []
        sep = "\n" if self._text_buffer else ""
        self._text_buffer = f"{self._text_buffer}{sep}{line}"
        return []

    def _flush_text_buffer(self) -> list[str]:
        text = self._text_buffer
        self._text_buffer = ""
        return self._emit_text_block(text)

    def flush(self) -> list[str]:
        out: list[str] = []
        if self._pending:
            tail = self._pending
            self._pending = ""
            out.extend(self._consume_line(tail))
        out.extend(self._flush_text_buffer())
        if self._in_code:
            out.extend(self._emit_code_block(self._code_lang, self._code_lines))
            self._in_code = False
            self._code_lines = []
        return out
