from myorch.bridge.markdown import markdown_to_irc


def test_bold_wraps_text_with_ctcp_bold():
    assert markdown_to_irc("hello **world** done") == "hello \x02world\x02 done"


def test_italic_uses_unicode_italic_marker():
    assert markdown_to_irc("a *quick* brown") == "a \x1Dquick\x1D brown"


def test_bold_takes_priority_over_italic():
    out = markdown_to_irc("**both *worlds* now**")
    assert out.startswith("\x02") and out.endswith("\x02")


def test_inline_code_uses_monospace_marker():
    assert markdown_to_irc("use `foo()` later") == "use \x11foo()\x11 later"


def test_h1_header_becomes_bold_with_color():
    assert markdown_to_irc("# Title") == "\x0307\x02Title\x02\x0F"


def test_list_item_replaces_dash_with_bullet():
    assert markdown_to_irc("- one\n- two") == "· one\n· two"


def test_link_renders_text_then_url_in_parens():
    assert (
        markdown_to_irc("see [docs](https://example.com)")
        == "see docs (https://example.com)"
    )


def test_round_trip_paragraph_unchanged_when_no_markup():
    assert markdown_to_irc("plain text only") == "plain text only"


def test_bold_does_not_swallow_unmatched_stars():
    assert markdown_to_irc("a * b") == "a * b"


def test_pre_existing_irc_colors_are_preserved():
    assert markdown_to_irc("\x0304red\x0F text") == "\x0304red\x0F text"
