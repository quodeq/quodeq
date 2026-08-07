"""Replay the scope gate over a real self-scan and pin the counts.

The synthetic fixtures prove each rule fires; they cannot prove the rules
COVER what they were designed to cover. During design, two coverage claims
survived a green unit suite and were only caught by replaying this run.

Skipped when the evaluation is not present (CI, other machines).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from quodeq.analysis.mcp.provenance_gate import apply_provenance_gate
from quodeq.analysis.mcp.scope_gate import apply_scope_gate
from quodeq.context.trust_model import CONSERVATIVE, TrustModel

_RUN = Path.home() / ".quodeq/evaluations/d33f1fd0-d685-4c3c-97f5-9ae26a1b3723"
_SECURITY = _RUN / "3a19b93f-1e01-428a-9d38-fea8e8929e63/evaluation/security.json"

pytestmark = pytest.mark.skipif(
    not _SECURITY.is_file(), reason="self-scan run 3a19b93f not present on this machine")

LOCAL = TrustModel(multi_tenant=False, network_exposure="loopback")


def _violations(severity: str):
    data = json.loads(_SECURITY.read_text(encoding="utf-8"))
    return [v for v in data["violations"] if v["severity"] == severity]


def _finding(v: dict, severity: str) -> dict:
    return {"t": "violation", "req": v.get("req"), "severity": severity,
            "w": v["title"], "reason": v["reason"], "file": v["file"]}


def _majors():
    return _violations("major")


def test_replay_counts_match_the_spec():
    majors = _majors()
    assert len(majors) == 77, "fixture run drifted; re-derive the expected counts"

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

    assert hits["sourceless_path"] == 32, hits
    assert hits["cross_principal"] == 1, hits
    assert demoted == 33, hits
    assert len(majors) - demoted == 44


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


def test_replay_chains_provenance_then_scope_on_criticals():
    """Every other test in this module calls apply_scope_gate directly on
    findings already labeled major, so the ordinary finding-sink pipeline
    (apply_provenance_gate runs first and guards the critical bar; only what
    survives it can ever reach apply_scope_gate as major) is never exercised
    end to end. Chain both gates, in production order, over the run's real
    criticals and observe what actually happens.

    Observed on the pinned run: 2 of the 4 criticals name only an
    operator-controlled source ("command-line arguments", an environment
    variable) -- apply_provenance_gate drops those to major, because that is
    not remote ingress. apply_scope_gate then leaves both alone: its
    sourceless_path rule requires NO named source at all, and an
    operator-controlled source is still a named source, so it does not
    double-dip on a finding provenance_gate already downgraded. The other 2
    criticals name proven external ingress ("query parameter",
    "user-provided") and neither gate touches them. Net effect: 2 stay
    critical, 2 become major, zero reach minor, zero scope_gate demotions
    fire after provenance_gate already ran.
    """
    criticals = _violations("critical")
    assert len(criticals) == 4, "fixture run drifted; re-derive the expected counts"

    provenance_hits = 0
    scope_hits = 0
    end_severities = Counter()
    for v in criticals:
        f = _finding(v, "critical")
        if apply_provenance_gate(f):
            provenance_hits += 1
        if apply_scope_gate(f, LOCAL):
            scope_hits += 1
        end_severities[f["severity"]] += 1

    assert provenance_hits == 2, end_severities
    assert scope_hits == 0, end_severities
    assert end_severities == Counter({"critical": 2, "major": 2}), end_severities
