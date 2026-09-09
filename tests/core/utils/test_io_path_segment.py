"""Parity between path_segment_error and validate_path_segment
(core/utils/io.py): the checker must return exactly the message the raising
twin raises."""
from __future__ import annotations

import pytest

from quodeq.core.utils.io import path_segment_error, validate_path_segment

_BAD_SEGMENTS = ["..", "a/b", "a\\b", "a\0b", "../etc/passwd", "a/../b"]
_GOOD_SEGMENTS = ["abc", "abc-123_v1.0", "run.42", "a_b-c.d"]


@pytest.mark.parametrize("bad", _BAD_SEGMENTS)
def test_matches_raised_message(bad):
    with pytest.raises(ValueError) as excinfo:
        validate_path_segment(bad)
    assert path_segment_error(bad) == str(excinfo.value)


@pytest.mark.parametrize("good", _GOOD_SEGMENTS)
def test_none_for_valid_segment(good):
    assert path_segment_error(good) is None
    validate_path_segment(good)  # must not raise


def test_reports_first_offending_segment():
    # Multiple segments: the checker must flag the *first* bad one, matching
    # the raising twin's for-loop order.
    with pytest.raises(ValueError) as excinfo:
        validate_path_segment("ok", "..", "also-bad/slash")
    assert path_segment_error("ok", "..", "also-bad/slash") == str(excinfo.value)


def test_all_valid_segments_return_none():
    assert path_segment_error(*_GOOD_SEGMENTS) is None
    validate_path_segment(*_GOOD_SEGMENTS)  # must not raise
