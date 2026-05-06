from myorch.bridge.codeblock import CodeBlockBuffer
from myorch.irc.messages import parse_line


def test_plain_text_passes_through():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("Hello world.")
    out += buf.flush()
    assert len(out) == 1
    msg = parse_line(out[0])
    assert msg.params[1] == "Hello world."
    assert msg.tags["+myorch.kind"] == "text"


def test_multiline_text_uses_multiline_batch():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("first paragraph\nsecond paragraph")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    assert parsed[0].command == "BATCH"
    assert parsed[0].params[1] == "draft/multiline"
    bodies = [p.params[1] for p in parsed if p.command == "PRIVMSG"]
    assert bodies == ["first paragraph", "second paragraph"]


def test_python_fenced_block_emits_codeblock_batch():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    text = "intro\n```python\ndef foo():\n    return 42\n```\noutro"
    out = buf.feed(text)
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    open_batches = [p for p in parsed if p.command == "BATCH" and p.params[0].startswith("+")]
    assert any(p.tags.get("+myorch.codeblock") == "python" for p in open_batches)
    code_lines = [
        p.params[1]
        for p in parsed
        if p.command == "PRIVMSG" and p.tags.get("batch")
    ]
    assert code_lines == ["def foo():", "    return 42"]
    text_lines = [
        p.params[1]
        for p in parsed
        if p.command == "PRIVMSG"
        and p.tags.get("+myorch.kind") == "text"
        and not p.tags.get("batch")
    ]
    assert "intro" in text_lines
    assert "outro" in text_lines


def test_unlanguaged_fence_uses_text_lang():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("```\nA\nB\n```")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    assert any(p.tags.get("+myorch.codeblock") == "text" for p in parsed if p.command == "BATCH")


def test_unterminated_fence_at_eof_still_flushes():
    buf = CodeBlockBuffer(channel="#p", session_id="s", turn_id=1)
    out = buf.feed("```python\nincomplete")
    out += buf.flush()
    parsed = [parse_line(l) for l in out]
    code_lines = [p.params[1] for p in parsed if p.command == "PRIVMSG" and p.tags.get("batch")]
    assert code_lines == ["incomplete"]
