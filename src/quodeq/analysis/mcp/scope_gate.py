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

# Reqs whose OWN premise is remote reachability (S-INT-10 is literally titled
# "externally controlled path"; S-AUT-10 covers cross-session/cross-tenant
# hijack over a request). A named external source there is relaxed under
# loopback, because the requirement's premise -- an untrusted party can reach
# this -- is exactly what the declaration says is false. S-AUT-3 is
# deliberately ABSENT: it is a general path/key-from-a-value finding with no
# such premise, so a genuinely named source (e.g. "request body") is real
# evidence that stays major regardless of the network declaration -- only its
# sourceless case (rule 1) is scope-dependent.
_INGRESS_REQS: frozenset[str] = frozenset({"S-INT-10", "S-AUT-10"})

# Concepts that only exist when there is more than one trust principal.
_CROSS_PRINCIPAL_TERMS: frozenset[str] = frozenset({
    "other user", "another user", "other users", "idor",
    "insecure direct object", "ownership verification", "ownership check",
    "tenant", "tenancy", "impersonate", "impersonation", "hijack",
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
    if (not model.multi_tenant and req in _CROSS_PRINCIPAL_REQS
            and _CROSS_PATTERN.search(prose)):
        return _downgrade(finding, "cross_principal")

    if not model.relaxes_remote():
        return False

    if req in _INGRESS_REQS and names_external_source(prose):
        return _downgrade(finding, "remote_ingress")

    if (req in _PATH_REQS
            and not names_external_source(prose)
            and not names_operator_source(prose)):
        return _downgrade(finding, "sourceless_path")

    return False
