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
PUBLIC = TrustModel(multi_tenant=False, network_exposure="public")


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


def test_cross_principal_untouched_when_public_single_tenant():
    # multi_tenant=False only says there is no SECOND user whose data could
    # be reached -- it says nothing about whether a stranger can reach the
    # process. S-AUT-10 also covers "Authorization checks MUST be enforced
    # on every request", so a public-facing single-user service missing an
    # authz check is genuinely vulnerable to an unauthenticated attacker.
    f = _finding(req="S-AUT-10", w="Session hijacking via IDOR",
                 reason="No ownership verification, so one user can reach "
                        "another user's terminal session.")
    assert apply_scope_gate(f, PUBLIC) is False
    assert f["severity"] == "major"


def test_cross_principal_untouched_when_lan_single_tenant():
    f = _finding(req="S-AUT-10", w="Session hijacking via IDOR",
                 reason="No ownership verification, so one user can reach "
                        "another user's terminal session.")
    assert apply_scope_gate(f, LAN) is False
    assert f["severity"] == "major"


def test_cross_principal_untouched_when_names_external_source():
    # The named ingress ("query parameter") supports a second reading the
    # cross-principal phrasing hides: an unauthenticated attacker reaching
    # the single user's own session via CSRF/DNS rebinding on the loopback
    # bind. multi_tenant=False rules out the SECOND-TENANT reading, but it
    # says nothing about this one, so the finding must stay major.
    f = _finding(req="S-AUT-10", w="IDOR via session id in query parameter",
                 reason="The session id is taken directly from a query "
                        "parameter and used to look up a terminal session "
                        "without ownership verification, allowing an "
                        "attacker to reach another user's active session.")
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_cross_principal_capped_when_naming_operator_source():
    # argv/env are the operator's own inputs, not an attacker channel, even
    # when the finding's premise is cross-principal: the operator-source
    # exclusion from rule 1 is deliberately NOT extended to this rule.
    f = _finding(req="S-AUT-10", w="Session hijacking via IDOR",
                 reason="The session id comes from a command-line argument "
                        "and is used to look up a terminal session without "
                        "ownership verification, allowing one user to reach "
                        "another user's session.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "cross_principal"


def test_cross_principal_matches_hijacking_gerund():
    # "hijack" gets an automatic s? suffix, matching "hijack"/"hijacks" but
    # not the -ing/-ed forms a real finding in the corpus uses ("Session
    # hijacking via IDOR"). "hijacking" and "hijacked" must be their own
    # terms, the same way "impersonate"/"impersonation" already are. This
    # reason deliberately contains no other cross-principal term (no "other
    # user", no "idor", no bare "hijack") so only the gerund can be doing
    # the matching.
    f = _finding(req="S-AUT-10", w="Session hijacking via session id reuse",
                 reason="The session id is predictable, allowing session "
                        "hijacking by a party who guesses it.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "cross_principal"


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


def test_cross_principal_evaluated_before_sourceless_path():
    # S-AUT-3 is the only req in BOTH _PATH_REQS and _CROSS_PRINCIPAL_REQS.
    # Construct prose that satisfies BOTH rules' evidence conditions at once:
    # sourceless (no external/operator source named) AND cross-principal
    # (names another user). Both rules would cap this the same way
    # (major -> minor), so the only observable difference is which rule name
    # lands in scope_downgrade["rule"] -- and that label is how someone later
    # audits what was waived, so the documented order (cross_principal first,
    # because it is more specific evidence) must actually hold in code, not
    # just in the comment.
    f = _finding(req="S-AUT-3",
                 reason="No ownership check, so one user can reach another "
                        "user's data via this path.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "cross_principal"


# --- I2: symmetric / idempotent under a tightened model --------------------

def test_scope_downgrade_is_restored_when_model_tightens():
    # A team declared loopback, scanned, and now honestly tightens their
    # profile to a hosted, multi-tenant model. A finding capped under the
    # old declaration must come back to major, not stay silently minor.
    f = _finding()
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"

    tightened = TrustModel(multi_tenant=True, network_exposure="public")
    assert apply_scope_gate(f, tightened) is True
    assert f["severity"] == "major"
    assert SCOPE_DOWNGRADE_MARKER not in f


def test_cross_principal_downgrade_is_restored_when_model_tightens():
    f = _finding(req="S-AUT-10", w="Session hijacking via IDOR",
                 reason="No ownership verification, so one user can reach "
                        "another user's terminal session.")
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"

    tightened = TrustModel(multi_tenant=True, network_exposure="public")
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
# ``scope_downgrade`` round-trips through the evidence JSONL, the cache,
# evaluation/<dim>.json, events.jsonl, and SQLite -- and every read seam on
# that path (finding_mappings._coerce_scope_downgrade, its twin in
# core/evidence/_jsonl.py, _report_parsing.build_finding,
# violations_parsing) only checks "dict" (some also require string values,
# but never checks WHICH string). A live report_finding MCP call can also
# set the field directly. Any of those seams can hand _restore a marker this
# gate never wrote. It must never raise, and must never write a severity
# other than "major" from it.

_TIGHTENED = TrustModel(multi_tenant=True, network_exposure="public")


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


# --- integration: wired into FindingEnricher.enrich ------------------------

from quodeq.analysis.mcp.enricher import CompiledContext, FindingEnricher


def _enricher(model):
    return FindingEnricher(CompiledContext(dimension="security", trust_model=model))


def test_enrich_applies_scope_gate():
    f = _enricher(LOCAL).enrich({
        "t": "violation", "req": "S-AUT-3", "severity": "major",
        "w": "Path traversal via job_id",
        "reason": "The job_id is used to construct a file path without validation.",
        "file": "src/app.py", "line": 10,
    })
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "sourceless_path"


def test_enrich_without_trust_model_is_unchanged():
    f = _enricher(None).enrich({
        "t": "violation", "req": "S-AUT-3", "severity": "major",
        "w": "Path traversal via job_id",
        "reason": "The job_id is used to construct a file path without validation.",
        "file": "src/app.py", "line": 10,
    })
    assert f["severity"] == "major"
