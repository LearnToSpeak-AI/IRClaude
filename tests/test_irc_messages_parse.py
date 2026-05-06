import pytest

from irclaude.irc.messages import Message, parse_line


def test_parse_simple_privmsg():
    msg = parse_line("PRIVMSG #foo :hello")
    assert msg.command == "PRIVMSG"
    assert msg.params == ["#foo", "hello"]
    assert msg.tags == {}
    assert msg.prefix is None


def test_parse_with_prefix_and_trailing():
    msg = parse_line(":nick!user@host PRIVMSG #foo :hello world")
    assert msg.prefix == "nick!user@host"
    assert msg.command == "PRIVMSG"
    assert msg.params == ["#foo", "hello world"]


def test_parse_message_tags():
    line = "@+irclaude.kind=text;+irclaude.session-id=abc PRIVMSG #foo :hi"
    msg = parse_line(line)
    assert msg.tags == {"+irclaude.kind": "text", "+irclaude.session-id": "abc"}
    assert msg.command == "PRIVMSG"
    assert msg.params == ["#foo", "hi"]


def test_parse_tag_without_value_is_empty_string():
    msg = parse_line("@draft/typing PRIVMSG #foo :ping")
    assert msg.tags == {"draft/typing": ""}


def test_parse_batch_open():
    line = "@batch=abc :server.local BATCH +abc draft/multiline #foo"
    msg = parse_line(line)
    assert msg.tags == {"batch": "abc"}
    assert msg.command == "BATCH"
    assert msg.params == ["+abc", "draft/multiline", "#foo"]


def test_parse_batch_close():
    msg = parse_line(":server.local BATCH -abc")
    assert msg.command == "BATCH"
    assert msg.params == ["-abc"]


def test_parse_multiline_concat_inside_batch():
    msg = parse_line("@batch=xy PRIVMSG #foo :    return 42")
    assert msg.tags["batch"] == "xy"
    assert msg.params == ["#foo", "    return 42"]


def test_parse_strips_crlf():
    msg = parse_line("PING :server.local\r\n")
    assert msg.command == "PING"
    assert msg.params == ["server.local"]


def test_parse_rejects_empty_line():
    with pytest.raises(ValueError):
        parse_line("")


def test_parse_rejects_only_tags():
    with pytest.raises(ValueError):
        parse_line("@only=tags")


def test_parse_decodes_tag_escapes():
    msg = parse_line("@key=a\\:b\\sc\\\\d\\rline\\nfeed CMD")
    assert msg.tags == {"key": "a;b c\\d\rline\nfeed"}
