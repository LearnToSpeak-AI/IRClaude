import pytest

from irclaude.irc.messages import parse_line
from irclaude.irc.protocol import encode_batch, encode_multiline, new_batch_id


def test_new_batch_id_is_unique_short_token():
    a = new_batch_id()
    b = new_batch_id()
    assert a != b
    assert len(a) <= 16
    assert all(ch.isalnum() for ch in a)


def test_encode_batch_wraps_lines():
    lines = encode_batch(
        batch_id="abc",
        type_="draft/multiline",
        tags={"+irclaude.codeblock": "python"},
        target="#foo",
        contents=["def hi():", "    return 42"],
    )
    assert len(lines) == 4  # open, two privmsgs, close
    open_msg = parse_line(lines[0])
    assert open_msg.command == "BATCH"
    assert open_msg.params[0] == "+abc"
    assert open_msg.params[1] == "draft/multiline"
    assert open_msg.params[2] == "#foo"
    assert open_msg.tags["+irclaude.codeblock"] == "python"

    privmsg1 = parse_line(lines[1])
    assert privmsg1.command == "PRIVMSG"
    assert privmsg1.params == ["#foo", "def hi():"]
    assert privmsg1.tags["batch"] == "abc"

    close_msg = parse_line(lines[3])
    assert close_msg.command == "BATCH"
    assert close_msg.params == ["-abc"]


def test_encode_multiline_splits_on_newlines():
    lines = encode_multiline(
        target="#foo",
        content="line one\nline two\nline three",
        tags={"+irclaude.kind": "text"},
    )
    privmsgs = [parse_line(l) for l in lines if " PRIVMSG " in l]
    assert [p.params[1] for p in privmsgs] == ["line one", "line two", "line three"]
    open_msg = parse_line(lines[0])
    assert open_msg.params[1] == "draft/multiline"
    assert open_msg.tags["+irclaude.kind"] == "text"


def test_encode_multiline_single_line_returns_one_privmsg():
    lines = encode_multiline(
        target="#foo",
        content="just one",
        tags={"+irclaude.kind": "text"},
    )
    assert len(lines) == 1
    p = parse_line(lines[0])
    assert p.command == "PRIVMSG"
    assert p.params == ["#foo", "just one"]


def test_encode_batch_rejects_empty_contents():
    with pytest.raises(ValueError):
        encode_batch(
            batch_id="x", type_="draft/multiline", tags={}, target="#foo", contents=[]
        )
