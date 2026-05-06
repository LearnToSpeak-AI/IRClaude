import pytest

from myorch.irc.messages import Message, parse_line


_FIXTURES = [
    "PRIVMSG #foo :hello\r\n",
    ":nick!user@host PRIVMSG #foo :hello world\r\n",
    "@+myorch.kind=text PRIVMSG #foo :hi\r\n",
    "@batch=abc;+myorch.kind=code PRIVMSG #foo :    return 42\r\n",
    "PING :server.local\r\n",
    "JOIN #foo\r\n",
    ":server.local 001 nick :Welcome to the network nick\r\n",
    "@key=a\\:b\\sc\\\\d\\rline\\nfeed CMD\r\n",
]


@pytest.mark.parametrize("wire", _FIXTURES)
def test_roundtrip_parse_encode_parse(wire: str):
    first = parse_line(wire)
    second_wire = first.encode()
    second = parse_line(second_wire)
    assert second.command == first.command
    assert second.params == first.params
    assert second.tags == first.tags
    assert second.prefix == first.prefix


def test_encode_emits_trailing_for_spaces():
    msg = Message(command="PRIVMSG", params=["#foo", "hello world"])
    assert msg.encode() == "PRIVMSG #foo :hello world\r\n"


def test_encode_emits_inline_for_simple_param():
    msg = Message(command="JOIN", params=["#foo"])
    assert msg.encode() == "JOIN #foo\r\n"


def test_encode_emits_tag_only_when_no_value():
    msg = Message(command="PRIVMSG", params=["#x", "hi"], tags={"draft/typing": ""})
    assert msg.encode().startswith("@draft/typing ")


def test_encode_escapes_tag_special_chars():
    msg = Message(
        command="X",
        tags={"k": "a;b c\\d\rline\nfeed"},
    )
    out = msg.encode()
    assert "\\:" in out
    assert "\\s" in out
    assert "\\\\" in out
    assert "\\r" in out
    assert "\\n" in out
