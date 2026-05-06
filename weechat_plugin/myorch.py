"""WeeChat plugin for myorch — render IRCv3 +myorch.* tagged events."""

import weechat


PLUGIN_NAME = "myorch"
PLUGIN_VERSION = "2.0.0"


_state: dict[str, object] = {
    "code_buffer_index": 0,
}


def _parse_tags(raw_tags: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for piece in raw_tags.split(";"):
        if not piece:
            continue
        if "=" in piece:
            k, v = piece.split("=", 1)
            out[k] = v
        else:
            out[piece] = ""
    return out


_BATCHES: dict[str, dict] = {}


_STATUS = {
    "channel": "?",
    "turn": 0,
    "agents": set(),
    "session": "",
}


def _next_code_buffer_name(channel: str) -> str:
    counters = _state.setdefault("code_counters", {})
    n = counters.get(channel, 0) + 1
    counters[channel] = n
    return f"code:{channel}:{n}"


def _highlight_to_irc(language: str, text: str) -> str:
    return text


def _begin_batch(batch_id: str, batch_type: str, channel: str, tags: dict) -> None:
    _BATCHES[batch_id] = {
        "channel": channel,
        "type": batch_type,
        "tags": tags,
        "lines": [],
    }


def _append_batch_line(batch_id: str, line: str) -> None:
    info = _BATCHES.get(batch_id)
    if info is None:
        return
    info["lines"].append(line)


def _close_batch(batch_id: str) -> None:
    info = _BATCHES.pop(batch_id, None)
    if info is None:
        return
    if info["tags"].get("+myorch.codeblock"):
        lang = info["tags"]["+myorch.codeblock"]
        buf_name = _next_code_buffer_name(info["channel"])
        weechat.buffer_new(buf_name, "", "", "", "")
        weechat.buffer_set(buf_name, "type", "free")
        weechat.buffer_set(buf_name, "title", f"{info['channel']} code [{lang}]")
        for idx, line in enumerate(info["lines"], start=1):
            weechat.prnt_y(buf_name, idx, _highlight_to_irc(lang, line))
        marker = f"[code ({lang}, {len(info['lines'])} lines) -> /buffer {buf_name}]"
        weechat.prnt(info["channel"], marker)


def cb_bar_status(data, item, window):
    return (
        f"proj={_STATUS['channel']}|"
        f"turn={_STATUS['turn']}|"
        f"agents={len(_STATUS['agents'])}"
    )


def cb_signal_join(data, signal, signal_data):
    parts = signal_data.split()
    if not parts:
        return weechat.WEECHAT_RC_OK()
    prefix = parts[0]
    if prefix.startswith(":"):
        nick = prefix[1:].split("!", 1)[0]
        if not nick.startswith("claude"):
            _STATUS["agents"].add(nick)
    return weechat.WEECHAT_RC_OK()


def cb_modifier_privmsg(data, modifier, modifier_data, line):
    parsed = weechat.info_get_hashtable("irc_message_parse", {"message": line})
    tags = _parse_tags(parsed.get("tags", ""))
    cmd = parsed.get("command", "")

    chan = parsed.get("channel") or _STATUS["channel"]
    if chan and chan.startswith("#"):
        _STATUS["channel"] = chan
    if "+myorch.turn-id" in tags:
        try:
            _STATUS["turn"] = int(tags["+myorch.turn-id"])
        except ValueError:
            pass
    if "+myorch.session-id" in tags:
        _STATUS["session"] = tags["+myorch.session-id"]

    if cmd == "BATCH":
        body = line.split()
        if len(body) >= 3 and body[-3].startswith("+"):
            batch_id = body[-3][1:]
            batch_type = body[-2]
            channel = body[-1]
            _begin_batch(batch_id, batch_type, channel, tags)
        elif body and body[-1].startswith("-"):
            _close_batch(body[-1][1:])
        return line

    if cmd == "PRIVMSG" and tags.get("batch"):
        batch_id = tags["batch"]
        text = parsed.get("arguments", "")
        _append_batch_line(batch_id, text)
        return ""

    kind = tags.get("+myorch.kind") or tags.get("myorch.kind")
    if not kind:
        return line
    return line


def shutdown_cb():
    return weechat.WEECHAT_RC_OK()


weechat.register(
    PLUGIN_NAME,
    "ipena",
    PLUGIN_VERSION,
    "MIT",
    "MyOrchestrator IRC bridge plugin",
    "shutdown_cb",
    "",
)
weechat.hook_modifier("irc_in2_privmsg", cb_modifier_privmsg, "")
weechat.bar_item_new("myorch_status", cb_bar_status, "")
weechat.hook_signal("*,irc_in2_join", cb_signal_join, "")
