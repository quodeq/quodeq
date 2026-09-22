"""Scope gate under a tightened model: restore, foreign markers, stale markers."""
from __future__ import annotations

import pytest

from quodeq.analysis.mcp.scope_gate import (
    SCOPE_DOWNGRADE_MARKER,
    apply_scope_gate,
)
from quodeq.context.trust_model import CONSERVATIVE, TrustModel

from ._scope_gate_helpers import LOCAL, SINGLE_HOST, _finding


# --- I2: symmetric / idempotent under a tightened model --------------------

def test_scope_downgrade_is_restored_when_model_tightens():
    # A team declared loopback, scanned, and now honestly tightens their
    # profile to a hosted, multi-tenant model. A finding capped under the
    # old declaration must come back to major, not stay silently minor.
    f = _finding()
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"

    tightened = TrustModel(multi_tenant=True, network_exposure="public",
                           deployment_topology="distributed")
    assert apply_scope_gate(f, tightened) is True
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_cross_principal_downgrade_is_restored_when_model_tightens():
    f = _finding(req="S-AUT-10", w="Session hijacking via IDOR",
                 reason="No ownership verification, so one user can reach "
                        "another user's terminal session.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"

    tightened = TrustModel(multi_tenant=True, network_exposure="public",
                           deployment_topology="distributed")
    assert apply_scope_gate(f, tightened) is True
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_restore_then_relax_again_downgrades_again():
    # Full round trip: loosen -> tighten -> loosen must re-cap, proving the
    # restore path does not leave the finding permanently major.
    f = _finding()
    apply_scope_gate(f, LOCAL)
    apply_scope_gate(f, CONSERVATIVE)
    assert f["severity"] == "major"

    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "sourceless_path"


def test_repeated_application_stable_once_downgraded():
    f = _finding()
    apply_scope_gate(f, LOCAL)
    for _ in range(3):
        assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "minor"


def test_repeated_application_stable_once_restored():
    f = _finding()
    apply_scope_gate(f, LOCAL)
    apply_scope_gate(f, CONSERVATIVE)
    for _ in range(3):
        assert apply_scope_gate(f, CONSERVATIVE) is False
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_topology_cap_restored_when_profile_widens():
    # A team declared single-host, scanned, then honestly starts scaling out.
    # A scalability finding capped under the old declaration must come back.
    f = _finding(req="F-SCL-1",
                 w="Session state is held in a process-local dict",
                 reason="State must be externalised to survive a second replica.")
    assert apply_scope_gate(f, SINGLE_HOST) is True
    assert f["severity"] == "minor"

    widened = TrustModel(multi_tenant=False, network_exposure="loopback",
                         deployment_topology="distributed")
    assert apply_scope_gate(f, widened) is True
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_topology_cap_is_idempotent():
    f = _finding(req="F-SCL-1",
                 w="Session state is held in a process-local dict",
                 reason="State must be externalised to survive a second replica.")
    assert apply_scope_gate(f, SINGLE_HOST) is True
    assert apply_scope_gate(f, SINGLE_HOST) is False
    assert f["severity"] == "minor"


def test_marker_left_alone_when_model_is_none():
    # Absence of model information must never move a score in either
    # direction -- the same no-regression guarantee the rest of this module
    # gives the forward (downgrade) direction.
    f = _finding()
    apply_scope_gate(f, LOCAL)
    assert apply_scope_gate(f, None) is False
    assert f["severity"] == "minor"
    assert SCOPE_DOWNGRADE_MARKER in f


# --- CRITICAL: _restore must reject a marker it did not write --------------
#
# ``scope_downgrade`` can reach the gate carrying a value this gate never
# wrote: a live ``report_finding`` MCP call is not schema-restricted to the
# declared fields and can set the field directly, and ``stream/parser.py``
# extracts a model's raw stdout JSONL verbatim, scope_downgrade included,
# without validating it. It must never raise, and must never write a
# severity other than "major" from it.

_TIGHTENED = TrustModel(multi_tenant=True, network_exposure="public",
                        deployment_topology="distributed")


@pytest.mark.parametrize("marker", [
    {"from": "critical"},   # would promote past what the gate ever put here,
                             # and past apply_provenance_gate
    {"from": "blocker"},    # not in the sqlite CHECK constraint's allowed set
    {"from": None},         # NOT NULL violation on insert
    {"from": 42},           # NOT NULL violation on insert
    {"rule": "sourceless_path", "to": "minor"},  # missing "from" entirely
    "sourceless_path",      # marker is a bare string, not a dict
    ["sourceless_path"],    # marker is a list
    True,                   # marker is a bool
], ids=[
    "from-critical", "from-blocker", "from-none", "from-42",
    "missing-from", "string-marker", "list-marker", "bool-marker",
])
def test_restore_rejects_a_marker_it_did_not_write(marker):
    f = _finding(severity="minor")
    f[SCOPE_DOWNGRADE_MARKER] = marker

    # Nothing must raise, severity must not move, and the untrustworthy
    # marker must not survive to be checked again on the next replay.
    assert apply_scope_gate(f, _TIGHTENED) is False
    assert f["severity"] == "minor"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_restore_accepts_the_marker_the_gate_actually_writes():
    # The one shape _downgrade ever produces must still restore correctly --
    # the rejection above must not have turned into a blanket no-op.
    f = _finding()
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"

    assert apply_scope_gate(f, _TIGHTENED) is True
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


# --- IMPORTANT: a stale marker on a non-minor finding is cleared -----------

def test_stale_marker_cleared_on_major_finding_when_rule_no_longer_fires():
    # A finding was capped to minor, then something outside this gate (a
    # corrupt cache entry, a hand-edited JSONL, a merge with a fresh live
    # finding at the same location) put its severity back to major without
    # going through _restore. The marker is now stale: it still claims the
    # finding was "capped to minor" even though it plainly isn't.
    f = _finding()
    apply_scope_gate(f, LOCAL)
    assert f["severity"] == "minor"
    f["severity"] = "major"

    assert apply_scope_gate(f, _TIGHTENED) is False
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_stale_marker_cleared_on_critical_finding_when_rule_no_longer_fires():
    f = _finding(severity="critical")
    f[SCOPE_DOWNGRADE_MARKER] = {"rule": "sourceless_path", "from": "major", "to": "minor"}

    assert apply_scope_gate(f, _TIGHTENED) is False
    assert f["severity"] == "critical"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_stale_marker_on_major_finding_left_alone_when_model_is_none():
    # Same no-regression guarantee as the restore direction: absence of
    # model information must not clear a marker either.
    f = _finding()
    apply_scope_gate(f, LOCAL)
    f["severity"] = "major"

    assert apply_scope_gate(f, None) is False
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER in f


def test_stale_marker_on_major_finding_refreshed_not_cleared_when_rule_still_fires():
    # If the rule that would justify the cap still fires, the marker isn't
    # stale -- it's re-earned, so the normal downgrade path re-caps the
    # finding rather than leaving a mismatched marker in place.
    f = _finding()
    apply_scope_gate(f, LOCAL)
    assert f["severity"] == "minor"
    f["severity"] = "major"

    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "sourceless_path"
