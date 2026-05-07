import re

from irclaude.bridge.codeblock import CodeBlockBuffer
from irclaude.irc.messages import parse_line


_IRC_COLOR = re.compile(r"\x03\d{0,2}(?:,\d{0,2})?|\x0F|\x02|\x1D|\x11|\x1F|\x1E|\x16")


def _strip_irc_codes(s: str) -> str:
    return _IRC_COLOR.sub("", s)


def test_plain_text_passes_through():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("Hello world.")
    out += buf.flush()
    assert len(out) == 1
    msg = parse_line(out[0])
    assert msg.params[1] == "Hello world."
    assert msg.tags["+irclaude.kind"] == "text"


def test_multiline_text_emits_one_privmsg_per_line():
    """WeeChat 4.1 doesn't surface assembled draft/multiline BATCHes to the
    print pipeline — content disappears. Bridge sends one PRIVMSG per line so
    each row renders with its own `<claude>` prefix."""
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("first paragraph\nsecond paragraph")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    assert all(p.command == "PRIVMSG" for p in parsed)
    bodies = [p.params[1] for p in parsed]
    assert bodies == ["first paragraph", "second paragraph"]


def test_python_fenced_block_emits_inline_with_lang_tag_and_borders():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    text = "intro\n```python\ndef foo():\n    return 42\n```\noutro"
    out = buf.feed(text)
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    open_batches = [p for p in parsed if p.command == "BATCH" and p.params[0].startswith("+")]
    code_open = [p for p in open_batches if p.tags.get("+irclaude.kind") == "code"]
    assert code_open, "expected a code-kind BATCH open"
    assert code_open[0].tags.get("+irclaude.lang") == "python"
    # +irclaude.codeblock is gone — code blocks are inline now, no separate buffer.
    assert "+irclaude.codeblock" not in code_open[0].tags
    code_lines = [
        _strip_irc_codes(p.params[1])
        for p in parsed
        if p.command == "PRIVMSG" and p.tags.get("batch")
    ]
    # Top + bottom border + code lines (Pygments adds IRC color codes between
    # tokens; assertions strip them so we can grep substrings directly).
    assert any("─── python ───" in l for l in code_lines)
    assert any("def foo():" in l for l in code_lines)
    assert any("return 42" in l for l in code_lines)
    text_lines = [
        p.params[1]
        for p in parsed
        if p.command == "PRIVMSG"
        and p.tags.get("+irclaude.kind") == "text"
        and not p.tags.get("batch")
    ]
    assert "intro" in text_lines
    assert "outro" in text_lines


def test_unlanguaged_fence_uses_text_lang():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("```\nA\nB\n```")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    code_open = [
        p for p in parsed
        if p.command == "BATCH" and p.params[0].startswith("+")
        and p.tags.get("+irclaude.kind") == "code"
    ]
    assert code_open
    assert code_open[0].tags.get("+irclaude.lang") == "text"


def test_unterminated_fence_at_eof_still_flushes():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("```python\nincomplete")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    code_lines = [
        _strip_irc_codes(p.params[1])
        for p in parsed
        if p.command == "PRIVMSG" and p.tags.get("batch")
    ]
    # Borders + 'incomplete' line.
    assert any("incomplete" in l for l in code_lines)


def test_bold_markdown_becomes_irc_bold_in_text():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("Es **controller**: un sistema Django")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    text = "".join(p.params[1] for p in parsed if p.command == "PRIVMSG")
    # \x02 is the IRC bold control character
    assert "\x02controller\x02" in text
    assert "**" not in text


def test_bold_inside_code_block_stays_literal():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("```python\nx = '**not bold**'\n```")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    code_text = " ".join(
        _strip_irc_codes(p.params[1])
        for p in parsed
        if p.command == "PRIVMSG" and p.tags.get("batch")
    )
    # Code is run through Pygments (IRC color codes), but the literal asterisks
    # of the string content survive — markdown_to_irc never gets to apply bold.
    assert "**not bold**" in code_text


def test_list_marker_becomes_bullet():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("- WiFi Analytics\n- Fixtures")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    text = " ".join(p.params[1] for p in parsed if p.command == "PRIVMSG")
    assert "· WiFi" in text
    assert "· Fixtures" in text
