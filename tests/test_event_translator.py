from myorch.bridge.event_translator import translate
from myorch.irc.messages import Message


def _kinds(msgs: list[Message]) -> list[str]:
    return [m.tags.get("+myorch.kind", "") for m in msgs]


def test_translate_assistant_text_emits_kind_text():
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "It defines foo."}]},
    }
    msgs = translate(event, channel="#proj", session_id="abc", turn_id=2)
    assert len(msgs) == 1
    assert msgs[0].command == "PRIVMSG"
    assert msgs[0].params == ["#proj", "It defines foo."]
    assert msgs[0].tags["+myorch.kind"] == "text"
    assert msgs[0].tags["+myorch.session-id"] == "abc"
    assert msgs[0].tags["+myorch.turn-id"] == "2"


def test_translate_tool_use_emits_status_with_tool_tag():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
            ]
        },
    }
    msgs = translate(event, channel="#proj", session_id="abc", turn_id=1)
    assert len(msgs) == 1
    assert msgs[0].tags["+myorch.kind"] == "tool-use"
    assert msgs[0].tags["+myorch.tool"] == "Bash"
    assert "Bash" in msgs[0].params[1]


def test_translate_tool_result_emits_kind_tool_result():
    event = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}
            ]
        },
    }
    msgs = translate(event, channel="#p", session_id="s", turn_id=1)
    assert _kinds(msgs) == ["tool-result"]


def test_translate_error_event_emits_kind_error():
    event = {"type": "error", "subtype": "model_error", "message": "rate limit"}
    msgs = translate(event, channel="#p", session_id="s", turn_id=1)
    assert _kinds(msgs) == ["error"]
    assert "rate limit" in msgs[0].params[1]


def test_translate_unknown_type_returns_empty_list():
    msgs = translate(
        {"type": "system", "subtype": "init"},
        channel="#p", session_id="s", turn_id=1,
    )
    assert msgs == []


def test_translate_assistant_with_multiple_text_blocks():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ]
        },
    }
    msgs = translate(event, channel="#p", session_id="s", turn_id=1)
    assert [m.params[1] for m in msgs] == ["first", "second"]
