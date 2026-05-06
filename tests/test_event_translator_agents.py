import json
from pathlib import Path

from irclaude.bridge.event_translator import classify_agent_events, translate


def _events():
    path = Path(__file__).parent / "fixtures" / "agent_dispatch.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_classify_agent_events_splits_starts_and_ends():
    events = _events()
    starts, ends, normal = classify_agent_events(events)
    assert [s["name"] for s in starts] == ["explore-1"]
    assert [e["name"] for e in ends] == ["explore-1"]
    assert len(normal) == 2


def test_translate_with_subagent_tag_emits_agent_msg():
    events = _events()
    sub_event = next(e for e in events if "subagent" in e)
    msgs = translate(sub_event, channel="#p", session_id="s", turn_id=1, agent_nick="explore-1")
    assert msgs[0].tags["+irclaude.kind"] == "agent-msg"
    assert msgs[0].tags["+irclaude.agent"] == "explore-1"
    assert msgs[0].params[1] == "found 3 files"


def test_translate_without_agent_nick_emits_text():
    events = _events()
    main_event = next(
        e for e in events if e["type"] == "assistant" and "subagent" not in e
    )
    msgs = translate(main_event, channel="#p", session_id="s", turn_id=1)
    assert msgs[0].tags["+irclaude.kind"] == "text"
