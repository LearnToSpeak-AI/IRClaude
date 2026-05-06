from dataclasses import dataclass, field

_TAG_UNESCAPE = {
    ":": ";",
    "s": " ",
    "\\": "\\",
    "r": "\r",
    "n": "\n",
}
_TAG_ESCAPE = {v: k for k, v in _TAG_UNESCAPE.items()}


def _unescape_tag_value(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append(_TAG_UNESCAPE.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _escape_tag_value(raw: str) -> str:
    out: list[str] = []
    for ch in raw:
        repl = _TAG_ESCAPE.get(ch)
        if repl is not None:
            out.append("\\" + repl)
        else:
            out.append(ch)
    return "".join(out)


@dataclass(frozen=True)
class Message:
    command: str
    params: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    prefix: str | None = None

    def encode(self) -> str:
        parts: list[str] = []
        if self.tags:
            tag_parts = []
            for k, v in self.tags.items():
                if v == "":
                    tag_parts.append(k)
                else:
                    tag_parts.append(f"{k}={_escape_tag_value(v)}")
            parts.append("@" + ";".join(tag_parts))
        if self.prefix:
            parts.append(":" + self.prefix)
        parts.append(self.command)
        if self.params:
            head = self.params[:-1]
            tail = self.params[-1]
            parts.extend(head)
            if " " in tail or tail.startswith(":") or tail == "":
                parts.append(":" + tail)
            else:
                parts.append(tail)
        return " ".join(parts) + "\r\n"


def parse_line(line: str) -> Message:
    if line is None:
        raise ValueError("line must be a string")
    line = line.rstrip("\r\n")
    if not line:
        raise ValueError("empty IRC line")

    tags: dict[str, str] = {}
    prefix: str | None = None

    if line.startswith("@"):
        end = line.find(" ")
        if end == -1:
            raise ValueError("tags without command")
        raw_tags = line[1:end]
        line = line[end + 1 :].lstrip()
        for piece in raw_tags.split(";"):
            if not piece:
                continue
            if "=" in piece:
                k, v = piece.split("=", 1)
                tags[k] = _unescape_tag_value(v)
            else:
                tags[piece] = ""

    if line.startswith(":"):
        end = line.find(" ")
        if end == -1:
            raise ValueError("prefix without command")
        prefix = line[1:end]
        line = line[end + 1 :].lstrip()

    if not line:
        raise ValueError("missing command")

    params: list[str] = []
    while line:
        if line.startswith(":"):
            params.append(line[1:])
            line = ""
            break
        sp = line.find(" ")
        if sp == -1:
            params.append(line)
            line = ""
        else:
            params.append(line[:sp])
            line = line[sp + 1 :].lstrip()

    command = params.pop(0)
    return Message(command=command.upper(), params=params, tags=tags, prefix=prefix)
