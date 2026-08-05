"""Tests for the declared-threat-model severity gate."""
from __future__ import annotations

import pytest

from quodeq.analysis.mcp.scope_gate import (
    SCOPE_DOWNGRADE_MARKER,
    apply_scope_gate,
)
from quodeq.context.trust_model import CONSERVATIVE, TrustModel

LOCAL = TrustModel(multi_tenant=False, network_exposure="loopback")
LAN = TrustModel(multi_tenant=False, network_exposure="lan")


def _finding(**kw) -> dict:
    base = {"t": "violation", "req": "S-AUT-3", "severity": "major",
            "w": "Path traversal via job_id",
            "reason": "The job_id is used to construct a file path without validation."}
    base.update(kw)
    return base


# --- rule 1: sourceless path hardening ------------------------------------

def test_sourceless_path_capped_under_loopback():
    f = _finding()
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "sourceless_path"
    assert f[SCOPE_DOWNGRADE_MARKER]["from"] == "major"
    assert f[SCOPE_DOWNGRADE_MARKER]["to"] == "minor"


def test_sourceless_path_untouched_under_conservative():
    # The no-regression guarantee, at the gate.
    f = _finding()
    assert apply_scope_gate(f, CONSERVATIVE) is False
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_lan_does_not_relax():
    f = _finding()
    assert apply_scope_gate(f, LAN) is False
    assert f["severity"] == "major"


def test_named_external_source_is_not_sourceless():
    # An actual request-fed path stays major even on a loopback project: the
    # rule is about unproven provenance, not about waiving real ingress.
    f = _finding(reason="The filename comes straight from the request body.")
    apply_scope_gate(f, LOCAL)
    assert f["severity"] == "major"


def test_operator_source_is_not_sourceless():
    f = _finding(reason="The output path is taken from a command-line argument.")
    apply_scope_gate(f, LOCAL)
    assert f["severity"] == "major"


def test_r_ft_2_is_excluded_from_rule_one():
    # 87 reliability null-guard findings live here. Their severity does not
    # turn on network exposure, so this gate must not touch them.
    f = _finding(req="R-FT-2",
                 reason="The argument is dereferenced without a null guard.")
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "major"


# --- rule 2: cross-principal ----------------------------------------------

def test_cross_principal_capped_when_single_tenant():
    f = _finding(req="S-AUT-10", w="Session hijacking via IDOR",
                 reason="No ownership verification, so one user can reach "
                        "another user's terminal session.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "cross_principal"


def test_cross_principal_untouched_when_multi_tenant():
    f = _finding(req="S-AUT-10",
                 reason="No ownership verification, so one user can reach "
                        "another user's terminal session.")
    model = TrustModel(multi_tenant=True, network_exposure="loopback")
    assert apply_scope_gate(f, model) is False
    assert f["severity"] == "major"


# --- rule 3: remote ingress -----------------------------------------------

def test_remote_ingress_capped_under_loopback():
    f = _finding(req="S-INT-10",
                 reason="The path is taken from a query parameter without validation.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "remote_ingress"


# --- invariants -----------------------------------------------------------

def test_never_touches_critical():
    # The critical bar belongs to the provenance gate. Two gates writing the
    # same field at the same severity would make the result order-dependent.
    f = _finding(severity="critical")
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "critical"


def test_never_touches_minor():
    f = _finding(severity="minor")
    assert apply_scope_gate(f, LOCAL) is False


def test_never_touches_compliance():
    f = _finding(t="compliance")
    assert apply_scope_gate(f, LOCAL) is False


def test_ignores_non_gated_req():
    f = _finding(req="S-ACC-6", reason="Unbounded read with no size limit.")
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "major"


def test_none_model_is_a_no_op():
    f = _finding()
    assert apply_scope_gate(f, None) is False
    assert f["severity"] == "major"


def test_never_drops_a_finding():
    f = _finding()
    apply_scope_gate(f, LOCAL)
    assert f["severity"] in ("minor", "major")
    assert f.get("w"), "the finding must survive intact, only its severity moves"
