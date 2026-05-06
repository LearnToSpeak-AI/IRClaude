import re

from irclaude.irc.protocol import encode_batch, encode_multiline, new_batch_id


_FENCE = re.compile(r"^```(\S*)\s*$")


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
        return encode_multiline(target=self.channel, content=text, tags=tags)

    def _emit_code_block(self, lang: str, lines: list[str]) -> list[str]:
        if not lines:
            return []
        tags = self._common_tags()
        tags["+irclaude.kind"] = "code"
        tags["+irclaude.codeblock"] = lang
        return encode_batch(
            batch_id=new_batch_id(),
            type_="draft/multiline",
            tags=tags,
            target=self.channel,
            contents=lines,
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
