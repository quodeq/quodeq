"""Deterministic severity gate for a project's DECLARED threat model.

``provenance_gate`` answers "where did this value come from?" and guards the
``critical`` bar. This module answers a different question -- "is there anyone
this finding's attacker could be?" -- and guards the ``major`` bar.

The distinction matters, because this is a CHANGE to the standard rather than
enforcement of it. ``evaluation_rules.md`` criterion 7 says a finding whose
source cannot be named is legitimately ``major``. That is right by default. It
stops being right once a project has declared that no untrusted party can reach
the process at all, and only that declaration gives this gate its authority --
which is why an undeclared project resolves to
``trust_model.CONSERVATIVE`` and nothing here fires.

The gate ships three rules -- ``sourceless_path``, ``cross_principal`` and
``single_host_topology``. Which one a finding's evidence earns lives in
``scope_gate_rules``; this module owns only what to DO about it. A finding
that names no scope-dependent concept is never touched.

Caps ``major`` -> ``minor``; never drops. A team that later ships as a hosted
service must be able to recover the list of what was waived, so the finding
survives with a ``scope_downgrade`` marker naming the rule that moved it.

The gate is SYMMETRIC. ``CacheKey`` deliberately excludes the trust model (see
its own comment), so a finding this gate capped under one declaration can
replay unchanged after the team tightens ``project-profile.json`` -- nothing
else in the pipeline re-derives severity from a stale marker. So every call
also checks the other direction: a finding already carrying a
``scope_downgrade`` marker whose rule no longer fires under the model it is
called with has its pre-gate severity restored and the marker removed. Both
directions are idempotent: a finding already at the state its current model
implies is left alone, so replaying the same model repeatedly is a no-op.
"""
from __future__ import annotations

import logging

from quodeq.analysis.mcp.scope_gate_rules import matched_rule
from quodeq.context.trust_model import TrustModel
from quodeq.core.finding_markers import SCOPE_DOWNGRADE

_log = logging.getLogger(__name__)

#: Additive output field describing why a severity moved. The name comes from
#: the marker registry rather than a literal here: the registry is what the
#: persistence guard enumerates, so a marker defined only at its producer is a
#: marker nothing checks the seams for.
SCOPE_DOWNGRADE_MARKER = SCOPE_DOWNGRADE


def _downgrade(finding: dict, rule: str) -> bool:
    finding[SCOPE_DOWNGRADE_MARKER] = {"rule": rule, "from": "major", "to": "minor"}
    finding["severity"] = "minor"
    _log.debug(
        "scope gate: %s capped %s finding to minor (%s)",
        rule, finding.get("req"), finding.get("file"),
    )
    return True


def _restore(finding: dict, marker: object) -> bool:
    """Restore *finding*'s severity from a ``scope_downgrade`` *marker*, but
    only when the marker is one this gate could plausibly have written
    itself.

    ``_downgrade`` only ever writes ``{"rule": ..., "from": "major", "to":
    "minor"}``, so anything else reaching here is corrupt or hostile: a live
    ``report_finding`` MCP call is not schema-restricted to the declared
    fields and can set ``scope_downgrade`` directly, and ``stream/parser.py``
    extracts a model's raw stdout JSONL verbatim, including any
    ``scope_downgrade`` value it contains, without validating it either.
    Trusting either would let unvalidated input dictate ``severity`` --
    including a promotion to ``critical`` that never passed
    ``apply_provenance_gate``, or a value like ``"blocker"`` that fails the
    ``findings.severity`` CHECK constraint and silently drops the row on
    insert.

    When the marker doesn't check out, drop it and leave ``severity`` exactly
    as found -- this gate must never raise, and must never write a severity
    it did not itself previously stamp.
    """
    if not isinstance(marker, dict) or marker.get("from") != "major":
        del finding[SCOPE_DOWNGRADE_MARKER]
        _log.debug(
            "scope gate: dropped an unrecognized scope_downgrade marker on "
            "%s finding, severity left at %s (%s)",
            finding.get("req"), finding.get("severity"), finding.get("file"),
        )
        return False

    finding["severity"] = "major"
    del finding[SCOPE_DOWNGRADE_MARKER]
    _log.debug(
        "scope gate: restored %s finding to major, marker %s no longer applies (%s)",
        finding.get("req"), marker.get("rule"), finding.get("file"),
    )
    return True


def _restore_or_clear_stale_marker(
    finding: dict, model: TrustModel | None, marker: object, severity: object,
) -> bool | None:
    """Handle a finding already carrying a ``scope_downgrade`` marker.

    Returns True/False when it fully decides ``apply_scope_gate``'s return
    value (a marker on a currently-minor finding, checked against *model*);
    returns None when the forward direction still needs evaluating (no
    marker, or the finding isn't minor) -- though as a side effect it may
    have cleared a marker that has gone stale on a non-minor finding.

    A finding already carrying the marker is checked against *model* first
    (see the module docstring's SYMMETRIC section): if the marker's rule no
    longer fires, its pre-gate severity is restored and the marker removed.
    When ``model is None`` (no resolved trust model -- e.g. an unwired call
    site) the marker is left exactly as it is: absence of information must
    never move a score in either direction, the same no-regression guarantee
    :data:`quodeq.context.trust_model.CONSERVATIVE` gives the forward
    direction.

    A marker surviving on a finding that is not (or is no longer) minor is
    stale: it documents a cap this gate is not currently enforcing, and left
    in place it would render in the UI as "capped to minor" on a finding
    that plainly isn't. Clear it once the model says the rule that would
    justify it does not fire. This does not count as changing the finding's
    severity, so it never causes this function to return True on its own.
    """
    if marker is not None and severity == "minor":
        if model is not None and matched_rule(finding, model) is None:
            return _restore(finding, marker)
        return False

    if (marker is not None and model is not None
            and matched_rule(finding, model) is None):
        del finding[SCOPE_DOWNGRADE_MARKER]
    return None


def apply_scope_gate(finding: dict, model: TrustModel | None) -> bool:
    """Cap a ``major`` finding the declared trust model puts out of scope, or
    restore one a PRIOR call capped that no longer qualifies under *model*.

    Returns True iff it changed the finding's severity, in either direction.
    The forward direction only ever touches ``major`` violations on a gated
    req: ``critical`` belongs to ``provenance_gate``, and letting both gates
    write the same field at the same severity would make the outcome depend
    on call order.
    """
    if finding.get("t") != "violation":
        return False

    marker = finding.get(SCOPE_DOWNGRADE_MARKER)
    severity = finding.get("severity")

    decided = _restore_or_clear_stale_marker(finding, model, marker, severity)
    if decided is not None:
        return decided

    if model is None:
        return False
    if severity != "major":
        return False

    rule = matched_rule(finding, model)
    if rule is None:
        return False
    return _downgrade(finding, rule)
