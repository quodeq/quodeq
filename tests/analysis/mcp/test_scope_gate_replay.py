"""Replay the scope gate over a real self-scan and pin the counts.

The synthetic fixtures prove each rule fires; they cannot prove the rules
COVER what they were designed to cover. During design, two coverage claims
survived a green unit suite and were only caught by replaying this run.

This is a CHARACTERIZATION replay: the counts below are pinned to the
committed fixture (``tests/analysis/fixtures/scope_gate_replay/``), reduced
from a real local self-scan (see that directory's README for provenance).
They are NOT a fixed spec — regenerating the fixture from a different run
requires recomputing and re-pinning every count in this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.mcp.scope_gate import apply_scope_gate
from quodeq.context.trust_model import CONSERVATIVE

from ._scope_gate_helpers import LOCAL

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/scope_gate_replay/security_findings.json"


def _violations(severity: str):
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return [v for v in data["violations"] if v["severity"] == severity]


def _finding(v: dict, severity: str) -> dict:
    return {"t": "violation", "req": v.get("req"), "severity": severity,
            "w": v["title"], "reason": v["reason"], "file": v["file"]}


def _majors():
    return _violations("major")


def test_replay_counts_match_the_spec():
    majors = _majors()
    assert len(majors) == 10, "fixture drifted; re-derive the expected counts"

    # remote_ingress was deleted (see scope_gate.py's module docstring and
    # the comment below _CROSS_PRINCIPAL_REQS) -- there is no third rule to
    # count here anymore.
    hits = {"sourceless_path": 0, "cross_principal": 0}
    demoted = 0
    for v in majors:
        f = _finding(v, "major")
        if apply_scope_gate(f, LOCAL):
            demoted += 1
            hits[f["scope_downgrade"]["rule"]] += 1
            assert f["severity"] == "minor"

    # This fixture's 10 majors (see the README's "Known limitation") happen
    # to trigger neither scope-gate rule -- a real, if unexciting, replay
    # outcome, not a placeholder. A future fixture regeneration from a
    # richer run is expected to produce non-zero hits here.
    assert hits["sourceless_path"] == 0, hits
    assert hits["cross_principal"] == 0, hits
    assert demoted == 0, hits
    assert len(majors) - demoted == 10


def test_replay_is_a_no_op_under_the_conservative_default():
    for v in _majors():
        f = _finding(v, "major")
        assert apply_scope_gate(f, CONSERVATIVE) is False


def test_the_one_real_bug_survives():
    """The unbounded r.read() in FetchClient must stay major: it is real, it
    needs no hostile actor, and no rule here has any business touching it."""
    for v in _majors():
        if "_fetch_client_class" not in v["file"]:
            continue
        f = _finding(v, "major")
        assert apply_scope_gate(f, LOCAL) is False
        return
    pytest.skip("unbounded-read finding not in this run")


def test_fixture_run_has_no_critical_violations():
    """Pin the fixture's "Known limitation": this run produced zero criticals.

    The chained replay this module was meant to exercise -- apply_provenance_gate
    first, guarding the critical bar, then apply_scope_gate on whatever survives
    as major -- needs a run that actually has criticals. Asserting it against
    this fixture would loop over an empty list and pass on nothing. Re-derive
    that test here once the fixture is regenerated from a run with criticals.
    """
    assert _violations("critical") == []
