"""utc_now_iso: the one format every services timestamp is stored in."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quodeq.shared.clock import utc_now_iso


def test_utc_now_iso_is_an_aware_utc_timestamp_close_to_now():
    before = datetime.now(timezone.utc)
    stamp = datetime.fromisoformat(utc_now_iso())
    after = datetime.now(timezone.utc)
    assert stamp.utcoffset() == timedelta(0)
    assert before <= stamp <= after


def test_utc_now_iso_keeps_the_plus_zero_offset_suffix():
    assert utc_now_iso().endswith("+00:00")
