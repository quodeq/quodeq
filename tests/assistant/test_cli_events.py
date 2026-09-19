"""_cli_events._raw_error_line: which non-JSON stdout lines count as errors."""
from __future__ import annotations

import pytest

from quodeq.assistant.adapters._cli_events import _BENIGN_RAW_LINES, _raw_error_line


def test_non_benign_line_is_reported_stripped():
    assert _raw_error_line("  boom: something failed  \n") == "boom: something failed"


@pytest.mark.parametrize("prefix", _BENIGN_RAW_LINES)
def test_benign_line_is_dropped(prefix):
    assert _raw_error_line(prefix + " trailing detail\n") is None


def test_blank_line_is_dropped():
    assert _raw_error_line("   \n") is None


def test_benign_prefix_must_start_the_line():
    """A benign phrase quoted mid-line is still a real error line."""
    line = f"error: {_BENIGN_RAW_LINES[0]}"
    assert _raw_error_line(line) == line
