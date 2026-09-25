"""Tally groups untagged findings by requirement code, not reason text.

A fresh self-evaluation carried 945 maintainability findings with no ``vt``,
944 distinct reasons and 30 distinct ``req`` codes. Grouping by reason made
the weighted volume equal the instance count, so the ceiling punished volume
and the score fell as coverage grew. ``req`` is the stable taxonomy every
finding already carries.
"""
from __future__ import annotations

from quodeq.core.scoring.internals import tally_types


def _v(severity: str, reason: str, req: str | None = None, vt: str | None = None) -> dict:
    item = {"severity": severity, "reason": reason}
    if req is not None:
        item["req"] = req
    if vt:
        item["vt"] = vt
    return item


def test_same_req_distinct_reasons_is_one_type():
    items = [
        _v("minor", "verdict strings inline", req="M-MDF-1"),
        _v("minor", "slider bounds repeated", req="M-MDF-1"),
        _v("minor", "chevron literal typed twice", req="M-MDF-1"),
    ]
    assert tally_types(items) == {"critical": 0, "major": 0, "minor": 1}


def test_distinct_req_are_distinct_types():
    items = [
        _v("minor", "a", req="M-MDF-1"),
        _v("minor", "b", req="M-MDF-1"),
        _v("minor", "c", req="M-REU-1"),
        _v("major", "d", req="M-MOD-3"),
    ]
    assert tally_types(items) == {"critical": 0, "major": 1, "minor": 2}


def test_vt_wins_over_req():
    items = [
        _v("minor", "a", req="M-MDF-1", vt="magic-number"),
        _v("minor", "b", req="M-MDF-1", vt="magic-string"),
    ]
    assert tally_types(items)["minor"] == 2


def test_reason_fallback_when_no_req():
    items = [_v("critical", "syntax error"), _v("critical", "wrong call signature")]
    assert tally_types(items)["critical"] == 2


def test_blank_req_falls_back_to_reason():
    items = [_v("minor", "a", req=""), _v("minor", "b", req="")]
    assert tally_types(items)["minor"] == 2


def test_same_req_across_severities_counts_per_bucket():
    items = [_v("major", "a", req="M-MOD-3"), _v("minor", "b", req="M-MOD-3")]
    assert tally_types(items) == {"critical": 0, "major": 1, "minor": 1}
