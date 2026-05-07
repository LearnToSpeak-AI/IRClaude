"""WeeChat plugin for irclaude — render IRCv3 +irclaude.* tagged events."""

import weechat


PLUGIN_NAME = "irclaude"
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


_STATUS = {
    "channel": "?",
    "turn": 0,
    "agents": set(),
    "session": "",
}


def cb_bar_status(data, item, window):
    return (
        f"proj={_STATUS['channel']}|"
        f"turn={_STATUS['turn']}|"
        f"agents={len(_STATUS['agents'])}"
    )


def cb_signal_join(data, signal, signal_data):
    parts = signal_data.split()
    if not parts:
        return weechat.WEECHAT_RC_OK
    prefix = parts[0]
    if prefix.startswith(":"):
        nick = prefix[1:].split("!", 1)[0]
        if not nick.startswith("claude"):
            _STATUS["agents"].add(nick)
    return weechat.WEECHAT_RC_OK


def cb_modifier_privmsg(data, modifier, modifier_data, line):
    # Defensive: must NEVER return anything other than the original line on
    # error. Returning None or raising silently drops the message in WeeChat,
    # which is how rendered chat output disappeared for the user.
    try:
        parsed = weechat.info_get_hashtable("irc_message_parse", {"message": line}) or {}
        tags = _parse_tags(parsed.get("tags", ""))

        chan = parsed.get("channel") or _STATUS["channel"]
        if chan and chan.startswith("#"):
            _STATUS["channel"] = chan
        if "+irclaude.turn-id" in tags:
            try:
                _STATUS["turn"] = int(tags["+irclaude.turn-id"])
            except ValueError:
                pass
        if "+irclaude.session-id" in tags:
            _STATUS["session"] = tags["+irclaude.session-id"]
    except Exception:
        pass
    return line


def cb_modifier_print(data, modifier, modifier_data, string):
    """mIRC-style nick wrap: `<nick>` instead of bare `nick` on chat lines.

    Defensive: any failure must return the original string so the print path
    isn't broken. Returning None would suppress the line entirely.
    """
    try:
        if "\t" not in string:
            return string
        if "irc_privmsg" not in modifier_data:
            return string
        prefix, _, message = string.partition("\t")
        if prefix.startswith("<"):
            return string
        return "<" + prefix + ">\t" + message
    except Exception:
        return string


def cb_command_irclaude(data, buffer, args):
    parts = args.split()
    if not parts:
        weechat.prnt(buffer, "/irclaude projects|recall|search|decisions|close|agents")
        return weechat.WEECHAT_RC_OK
    sub = parts[0]
    rest = " ".join(parts[1:])
    payload = f"!{sub}" + (f" {rest}" if rest else "")
    weechat.prnt(buffer, f"PRIVMSG claude :{payload}")
    return weechat.WEECHAT_RC_OK


def shutdown_cb():
    return weechat.WEECHAT_RC_OK


weechat.register(
    PLUGIN_NAME,
    "Ivan Pena",
    PLUGIN_VERSION,
    "MIT",
    "IRClaude IRC bridge plugin",
    "shutdown_cb",
    "",
)
weechat.hook_modifier("irc_in2_privmsg", "cb_modifier_privmsg", "")
weechat.hook_modifier("irc_in2_batch", "cb_modifier_privmsg", "")
weechat.hook_modifier("weechat_print", "cb_modifier_print", "")
weechat.bar_item_new("irclaude_status", "cb_bar_status", "")
weechat.hook_signal("*,irc_in2_join", "cb_signal_join", "")
weechat.hook_command(
    "irclaude",
    "irclaude helpers",
    "[projects|recall|search|decisions|close|agents] <args>",
    "subcommand args",
    "",
    "cb_command_irclaude",
    "",
)
