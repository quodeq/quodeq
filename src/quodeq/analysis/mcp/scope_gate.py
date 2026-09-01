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

The gate ships two rules: rule 1 relaxes an unproven-provenance path/key
finding when the model declares no untrusted party can reach the process at
all, and rule 2 relaxes a finding whose premise is a second trust principal
when the model declares there is only one AND no untrusted party can reach
the process AND the finding's prose does not name an external source.
(Rule 2 is evaluated first in code, because its evidence is more specific
and would otherwise be masked by rule 1 -- see the comment on
``apply_scope_gate``.) The third precondition for rule 2 exists because
a finding whose prose names proven external ingress has a second reading the
cross-principal phrasing hides: an unauthenticated attacker reaching the
single user's own data via browser CSRF or DNS rebinding on the loopback
bind. Multi-tenant=False rules out the second-tenant reading, but it says
nothing about this one, so the finding must stay major when the prose
names how the stranger gets in. There is no third, remote-ingress rule;
the comment below ``_CROSS_PRINCIPAL_REQS`` records why.

Every rule requires BOTH a gated requirement id AND evidence in the model's
prose, the same two-condition shape ``provenance_gate`` uses. A finding that
names no scope-dependent concept is never touched.

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
import re

from quodeq.analysis.mcp.provenance_gate import (
    names_external_source,
    names_operator_source,
)
from quodeq.context.trust_model import TrustModel
from quodeq.core.finding_markers import SCOPE_DOWNGRADE

_log = logging.getLogger(__name__)

#: Additive output field describing why a severity moved. The name comes from
#: the marker registry rather than a literal here: the registry is what the
#: persistence guard enumerates, so a marker defined only at its producer is a
#: marker nothing checks the seams for.
SCOPE_DOWNGRADE_MARKER = SCOPE_DOWNGRADE

# Path-shaped requirements. R-FT-2 is deliberately ABSENT: it is the
# null-guard pattern, its severity does not turn on network exposure, and
# including it would sweep in ~87 reliability findings this gate has no
# opinion about.
_PATH_REQS: frozenset[str] = frozenset({"S-AUT-3", "S-INT-10"})
_CROSS_PRINCIPAL_REQS: frozenset[str] = frozenset({"S-AUT-10", "S-AUT-3"})

# There is deliberately no rule that relaxes a NAMED external source (e.g.
# "request body", "query parameter") under loopback, even for reqs like
# S-INT-10 whose own premise is remote reachability. A loopback bind is a
# runtime setting (QUODEQ_ACTION_API_HOST), not a code property: the code
# proves it reads attacker-controlled input regardless of how the process
# happens to be bound today. Waiving that would silently evaporate the
# moment someone rebinds the app to 0.0.0.0, and nothing would be left to
# re-flag it. Both rules honor this: rule 1 only fires on a SOURCELESS
# finding, and rule 2 (see its own comment in ``apply_scope_gate``) also
# backs off the instant the prose names an external source, even though its
# own trigger is a cross-principal concept, not provenance.

# Concepts that only exist when there is more than one trust principal. Every
# term already gets an automatic ``s?`` plural suffix below, so a plural form
# ("other users") is never listed separately -- only distinct WORD forms
# ("impersonate" / "impersonation", "hijack" / "hijacking" / "hijacked") need
# their own entry.
_CROSS_PRINCIPAL_TERMS: frozenset[str] = frozenset({
    "other user", "another user", "idor",
    "insecure direct object", "ownership verification", "ownership check",
    "tenant", "tenancy", "impersonate", "impersonation",
    "hijack", "hijacking", "hijacked",
})

_CROSS_PATTERN = re.compile(
    "|".join(rf"\b{re.escape(t)}s?\b"
             for t in sorted(_CROSS_PRINCIPAL_TERMS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _prose(finding: dict) -> str:
    """The model's natural-language evidence. The code snippet is never read,
    so the decision stays language-independent."""
    return " ".join(str(finding.get(k) or "") for k in ("reason", "w"))


def _cross_principal_rule_applies(model: TrustModel, req: str | None, prose: str) -> bool:
    """True when rule 2 (cross-principal) relaxes a finding under *model*.

    Both axes are required, not just ``multi_tenant``. ``multi_tenant=False``
    only says there is no SECOND user whose data could be reached -- it says
    nothing about whether a stranger can reach the process at all. S-AUT-10
    also covers "Authorization checks MUST be enforced on every request", so
    a public-facing single-user service with a missing authz check is still
    genuinely vulnerable: the attacker is an unauthenticated stranger, not a
    second tenant. Without ``relaxes_remote()`` here, this waiver would
    silently evaporate the moment the app becomes network-exposed, the same
    failure shape that got the old remote-ingress rule deleted (see the
    comment below ``_CROSS_PRINCIPAL_REQS``).

    The tenancy check alone is not enough either, which is why a provenance
    check joins it. "Another user's session" is ambiguous: it can describe a
    genuine second-tenant read (impossible once ``multi_tenant`` is False)
    OR it can describe an unauthenticated stranger reaching the SAME single
    user's own session -- still live on a loopback bind via browser CSRF or
    DNS rebinding -- when the finding also names how that stranger gets in
    (e.g. "query parameter"). The cross-principal phrasing cannot tell those
    two readings apart; ``names_external_source`` can, because it reads the
    ingress term instead of the relationship term. So both a tenancy check
    (rules out reading #1) and a provenance check (rules out reading #2) are
    required before this rule may relax anything.

    ``names_operator_source`` is deliberately NOT added alongside it: argv
    and the environment are the operator's own inputs, set by whoever
    launches the process, and carry no attacker reading here even when the
    finding's premise is cross-principal.
    """
    return bool(
        not model.multi_tenant and model.relaxes_remote()
        and req in _CROSS_PRINCIPAL_REQS
        and _CROSS_PATTERN.search(prose)
        and not names_external_source(prose)
    )


def _sourceless_path_rule_applies(model: TrustModel, req: str | None, prose: str) -> bool:
    """True when rule 1 (sourceless path/key) relaxes a finding under *model*."""
    if not model.relaxes_remote():
        return False
    return (req in _PATH_REQS
            and not names_external_source(prose)
            and not names_operator_source(prose))


def _matched_rule(finding: dict, model: TrustModel) -> str | None:
    """Return the rule name that would relax *finding* under *model*, or
    ``None``. Pure evidence check -- independent of the finding's CURRENT
    severity, so :func:`apply_scope_gate` can reuse it both to decide whether
    to downgrade a major finding and to decide whether a marker on an
    already-minor finding is still earned.

    Rule 2 (cross-principal) is checked first: a named cross-principal
    concept is more specific evidence than the absence of a source, and
    would otherwise be masked by rule 1 (sourceless path/key).
    """
    req = finding.get("req")
    prose = _prose(finding)

    if _cross_principal_rule_applies(model, req, prose):
        return "cross_principal"
    if _sourceless_path_rule_applies(model, req, prose):
        return "sourceless_path"
    return None


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
        if model is not None and _matched_rule(finding, model) is None:
            return _restore(finding, marker)
        return False

    if (marker is not None and model is not None
            and _matched_rule(finding, model) is None):
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

    rule = _matched_rule(finding, model)
    if rule is None:
        return False
    return _downgrade(finding, rule)
