"""_DdgResultParser: accumulate parts then join, instead of += per chunk.

Sibling to test_tools_web.py (already at the 240-line cap) rather than an
addition to it.
"""
from quodeq.assistant.tools._web_tools import _DdgResultParser

# The inline <b> inside the anchor forces the HTMLParser to hand handle_data
# several separate chunks ("Example ", "guide", " to it") while the "title"
# target is open, instead of one single call.
_SPLIT_TITLE_HTML = """
<html><body>
<div class="result">
  <h2 class="result__title">
    <a class="result__a" href="https://example.com/guide">Example <b>guide</b> to it</a>
  </h2>
  <a class="result__snippet" href="#">A <b>useful</b> guide.</a>
</div>
</body></html>
"""


def test_title_split_across_several_handle_data_calls_is_not_truncated():
    parser = _DdgResultParser()
    parser.feed(_SPLIT_TITLE_HTML)
    parser.close()
    assert parser.results[0]["title"] == "Example guide to it"
    assert parser.results[0]["snippet"] == "A useful guide."


def test_parts_are_joined_not_accumulated_with_plus_equals():
    """The parser must build the title from a list of parts joined once, not
    by repeated string += per handle_data call."""
    parser = _DdgResultParser()
    parser.feed('<div class="result"><h2 class="result__title">'
                 '<a class="result__a" href="https://example.com/guide">'
                 'Example <b>guide</b> to it')
    assert parser._parts == ["Example ", "guide", " to it"]
    parser.close()


def test_unterminated_target_tag_still_yields_its_text():
    """A target opened but never closed (malformed/truncated HTML) must
    still flush its accumulated parts when the parser is closed."""
    parser = _DdgResultParser()
    parser.feed('<div class="result"><h2 class="result__title">'
                 '<a class="result__a" href="https://example.com/x">Cut off mid')
    parser.close()
    assert parser.results[0]["title"] == "Cut off mid"
