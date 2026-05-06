from irclaude.bridge.markdown import markdown_to_irc


def test_bold_wraps_text_with_ctcp_bold():
    assert markdown_to_irc("hello **world** done") == "hello \x02world\x02 done"


def test_italic_uses_unicode_italic_marker():
    assert markdown_to_irc("a *quick* brown") == "a \x1Dquick\x1D brown"


def test_bold_takes_priority_over_italic():
    out = markdown_to_irc("**both *worlds* now**")
    assert out.startswith("\x02") and out.endswith("\x02")


def test_inline_code_uses_light_grey_color():
    # \x11 (IRC monospace) renders as a stray caret on many terminals;
    # we wrap in light grey + reset instead.
    assert markdown_to_irc("use `foo()` later") == "use \x0314foo()\x0F later"


def test_h1_header_becomes_bold_with_color():
    assert markdown_to_irc("# Title") == "\x0307\x02Title\x02\x0F"


def test_list_item_replaces_dash_with_bullet():
    assert markdown_to_irc("- one\n- two") == "· one\n· two"


def test_link_renders_text_underlined_then_url_in_parens():
    assert (
        markdown_to_irc("see [docs](https://example.com)")
        == "see \x1Fdocs\x1F (https://example.com)"
    )


def test_strikethrough_uses_irc_strikethrough_marker():
    assert markdown_to_irc("a ~~old~~ b") == "a \x1Eold\x1E b"


def test_blockquote_prefixes_with_colored_bar():
    out = markdown_to_irc("> remember to lock the door")
    assert out == "\x0314▌\x0F remember to lock the door"


def test_checklist_done_becomes_check_mark():
    out = markdown_to_irc("- [x] ship it")
    assert out.startswith("\x0303☑\x0F ")
    assert "ship it" in out


def test_checklist_todo_becomes_empty_box():
    out = markdown_to_irc("- [ ] write tests")
    assert out == "☐ write tests"


def test_table_renders_as_ascii_grid():
    md = (
        "| Value | Code |\n"
        "|-------|------|\n"
        "| READ  | 0    |\n"
        "| WRITE | 1    |\n"
    )
    out = markdown_to_irc(md)
    # tabulate's rounded_grid uses unicode box chars; check structure + values.
    assert "Value" in out
    assert "Code" in out
    assert "READ" in out
    assert "WRITE" in out
    # No raw markdown pipe-rows survive.
    assert "|-------|" not in out


def test_round_trip_paragraph_unchanged_when_no_markup():
    assert markdown_to_irc("plain text only") == "plain text only"


def test_bold_does_not_swallow_unmatched_stars():
    assert markdown_to_irc("a * b") == "a * b"


def test_pre_existing_irc_colors_are_preserved():
    assert markdown_to_irc("\x0304red\x0F text") == "\x0304red\x0F text"
