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
"""
from __future__ import annotations

import logging
import re

from quodeq.analysis.mcp.provenance_gate import (
    names_external_source,
    names_operator_source,
)
from quodeq.context.trust_model import TrustModel

_log = logging.getLogger(__name__)

#: Additive output field describing why a severity moved.
SCOPE_DOWNGRADE_MARKER = "scope_downgrade"

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


def _downgrade(finding: dict, rule: str) -> bool:
    finding[SCOPE_DOWNGRADE_MARKER] = {"rule": rule, "from": "major", "to": "minor"}
    finding["severity"] = "minor"
    _log.debug(
        "scope gate: %s capped %s finding to minor (%s)",
        rule, finding.get("req"), finding.get("file"),
    )
    return True


def apply_scope_gate(finding: dict, model: TrustModel | None) -> bool:
    """Cap a ``major`` finding the declared trust model puts out of scope.

    Returns True iff it downgraded. Only ever touches ``major`` violations on
    a gated req: ``critical`` belongs to ``provenance_gate``, and letting both
    gates write the same field at the same severity would make the outcome
    depend on call order.
    """
    if model is None:
        return False
    if finding.get("t") != "violation":
        return False
    if finding.get("severity") != "major":
        return False
    req = finding.get("req")
    prose = _prose(finding)

    # Rule 2 first: a named cross-principal concept is more specific evidence
    # than the absence of a source, and would otherwise be masked by rule 1.
    #
    # Both axes are required, not just ``multi_tenant``. ``multi_tenant=False``
    # only says there is no SECOND user whose data could be reached -- it says
    # nothing about whether a stranger can reach the process at all. S-AUT-10
    # also covers "Authorization checks MUST be enforced on every request", so
    # a public-facing single-user service with a missing authz check is still
    # genuinely vulnerable: the attacker is an unauthenticated stranger, not a
    # second tenant. Without ``relaxes_remote()`` here, this waiver would
    # silently evaporate the moment the app becomes network-exposed, the same
    # failure shape that got the old remote-ingress rule deleted (see the
    # comment below ``_CROSS_PRINCIPAL_REQS``).
    #
    # The tenancy check alone is not enough either, which is why a provenance
    # check joins it. "Another user's session" is ambiguous: it can describe a
    # genuine second-tenant read (impossible once ``multi_tenant`` is False)
    # OR it can describe an unauthenticated stranger reaching the SAME single
    # user's own session -- still live on a loopback bind via browser CSRF or
    # DNS rebinding -- when the finding also names how that stranger gets in
    # (e.g. "query parameter"). The cross-principal phrasing cannot tell those
    # two readings apart; ``names_external_source`` can, because it reads the
    # ingress term instead of the relationship term. So both a tenancy check
    # (rules out reading #1) and a provenance check (rules out reading #2) are
    # required before this rule may relax anything.
    #
    # ``names_operator_source`` is deliberately NOT added alongside it: argv
    # and the environment are the operator's own inputs, set by whoever
    # launches the process, and carry no attacker reading here even when the
    # finding's premise is cross-principal.
    if (not model.multi_tenant and model.relaxes_remote()
            and req in _CROSS_PRINCIPAL_REQS
            and _CROSS_PATTERN.search(prose)
            and not names_external_source(prose)):
        return _downgrade(finding, "cross_principal")

    if not model.relaxes_remote():
        return False

    if (req in _PATH_REQS
            and not names_external_source(prose)
            and not names_operator_source(prose)):
        return _downgrade(finding, "sourceless_path")

    return False
