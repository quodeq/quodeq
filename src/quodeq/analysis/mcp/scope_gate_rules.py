"""Which scope-gate rule, if any, a finding's evidence earns.

Split out of ``scope_gate`` so that module keeps only the mechanics of
applying and restoring a cap. This half is the evidence half: it reads a
finding's requirement id and prose and names the rule that fires, with no
knowledge of severities or markers. :func:`matched_rule` is the only entry
point.

The gate ships four rules:

* rule 1 (``sourceless_path``) relaxes an unproven-provenance path/key
  finding when the model declares no untrusted party can reach the process
  at all;
* rule 2 (``cross_principal``) relaxes a finding whose premise is a second
  trust principal when the model declares there is only one AND no
  untrusted party can reach the process AND the finding's prose does not
  name an external source;
* rule 3 (``single_host_topology``) relaxes a scalability finding whose
  premise is a multi-host deployment when the model declares the product
  runs as one process on one host;
* rule 4 (``loopback_transport``) relaxes a transport-encryption finding
  (S-CON-10) when the model declares no untrusted party can reach the
  process AND the finding's prose does not name an outbound destination.

Rule 2 is evaluated first in code, because its evidence is more specific and
would otherwise be masked by rule 1 -- see :func:`matched_rule`. The third
precondition for rule 2 exists because a finding whose prose names proven
external ingress has a second reading the cross-principal phrasing hides: an
unauthenticated attacker reaching the single user's own data via browser
CSRF or DNS rebinding on the loopback bind. Multi-tenant=False rules out the
second-tenant reading, but it says nothing about this one, so the finding
must stay major when the prose names how the stranger gets in. There is no
remote-ingress rule; the comment below ``_CROSS_PRINCIPAL_REQS`` records why.

Rules 1, 2 and 4 require BOTH a gated requirement id AND evidence in the
model's prose, the same two-condition shape ``provenance_gate`` uses. A
finding that names no scope-dependent concept is never touched. Rule 3 is
the one carve-out: it reads no prose, because its three requirement ids have
no second reading that survives a single-host declaration (see the comment
on ``_TOPOLOGY_REQS``).
"""
from __future__ import annotations

import re

from quodeq.analysis.mcp.provenance_gate import (
    names_external_source,
    names_operator_source,
)
from quodeq.context.trust_model import TrustModel

# Path-shaped requirements. R-FT-2 is deliberately ABSENT: it is the
# null-guard pattern, its severity does not turn on network exposure, and
# including it would sweep in ~87 reliability findings this gate has no
# opinion about.
_PATH_REQS: frozenset[str] = frozenset({"S-AUT-3", "S-INT-10"})
_CROSS_PRINCIPAL_REQS: frozenset[str] = frozenset({"S-AUT-10", "S-AUT-3"})

# Requirements whose entire premise is a multi-process, multi-host deployment:
# externalised state (F-SCL-1), a replaceable storage backend (F-SCL-2),
# horizontal dispatch (F-SCL-4). Unlike rules 1 and 2 this rule reads no prose
# -- the requirement id IS the evidence. There is no second reading of
# "externalise this state" that survives a declaration that the whole product
# is one process on one host.
_TOPOLOGY_REQS: frozenset[str] = frozenset({"F-SCL-1", "F-SCL-2", "F-SCL-4"})

# There is deliberately no rule that relaxes a NAMED external source (e.g.
# "request body", "query parameter") under loopback, even for reqs like
# S-INT-10 whose own premise is remote reachability. A loopback bind is a
# runtime setting (QUODEQ_ACTION_API_HOST), not a code property: the code
# proves it reads attacker-controlled input regardless of how the process
# happens to be bound today. Waiving that would silently evaporate the
# moment someone rebinds the app to 0.0.0.0, and nothing would be left to
# re-flag it. Both rules honor this: rule 1 only fires on a SOURCELESS
# finding, and rule 2 (see ``_cross_principal_rule_applies`` below) also
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


def _term_pattern(terms: frozenset[str] | set[str]) -> "re.Pattern[str]":
    """A case-insensitive alternation matching any of *terms* as a whole word.

    A trailing optional "s" covers the plural of each term, and the
    alternation is ordered longest-first so a longer phrase wins over a
    shorter one it contains.
    """
    return re.compile(
        "|".join(rf"\b{re.escape(t)}s?\b"
                 for t in sorted(terms, key=len, reverse=True)),
        re.IGNORECASE,
    )


_CROSS_PATTERN = _term_pattern(_CROSS_PRINCIPAL_TERMS)

# Rule 4: S-CON-10's entire premise ("sensitive data MUST be transmitted only
# over encrypted channels", CWE-319) is an on-path observer of traffic into
# this process. Under a DECLARED loopback exposure the only party who can
# observe that traffic is already code running as the same principal on the
# same machine, which can read the secret at rest anyway -- encrypting the
# channel defends against no one. This does not repeat the deleted
# remote-ingress failure recorded above ``_CROSS_PRINCIPAL_TERMS``: that rule
# waived findings whose code PROVABLY reads attacker-controlled input (a code
# property, true under any bind), whereas whether a channel needs encryption
# is, like rule 3's topology, purely a property of who can be on the wire --
# and if the declaration is later tightened, the gate's symmetric replay
# restores every capped finding.
_TRANSPORT_REQS: frozenset[str] = frozenset({"S-CON-10"})

# Same distinct-WORD-forms convention as ``_CROSS_PRINCIPAL_TERMS``. The
# prose condition is not decoration: models file non-transport findings
# under S-CON-10 too ("API key read from environment without encryption",
# "unvalidated URL passed to webbrowser.open"), and those name no channel
# for a loopback declaration to have an opinion about.
_TRANSPORT_TERMS: frozenset[str] = frozenset({
    "transmit", "transmitted", "transmitting", "transmission", "in transit",
    "cleartext", "clear text", "unencrypted", "encrypted channel",
    "https", "tls", "ssl", "sniff", "sniffed", "sniffing",
    "man-in-the-middle", "mitm",
})

_TRANSPORT_PATTERN = _term_pattern(_TRANSPORT_TERMS)

# The back-off. A loopback declaration states who can open a socket INTO the
# process; it says nothing about where the process SENDS data. A cleartext
# credential posted outbound to a third-party endpoint crosses a real wire
# whatever this process is bound to, so prose naming an outbound destination
# keeps its finding major -- the same never-waive-proven-egress posture as
# rule 2's ``names_external_source`` back-off, pointed the other direction.
_OUTBOUND_TERMS: frozenset[str] = frozenset({
    "outbound", "third-party", "third party", "external service",
    "external server", "external endpoint", "external api",
    "remote server", "remote host", "remote endpoint", "upstream",
})

_OUTBOUND_PATTERN = _term_pattern(_OUTBOUND_TERMS)


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


def _topology_rule_applies(model: TrustModel, req: str | None) -> bool:
    """True when rule 3 (single-host topology) relaxes a finding under *model*."""
    return bool(model.is_single_host() and req in _TOPOLOGY_REQS)


def _loopback_transport_rule_applies(model: TrustModel, req: str | None, prose: str) -> bool:
    """True when rule 4 (loopback transport) relaxes a finding under *model*.

    Two conditions and a back-off: the gated requirement id, prose naming a
    transport-encryption concept (the rationale lives on
    ``_TRANSPORT_REQS``), and no outbound destination in the prose (the
    rationale lives on ``_OUTBOUND_TERMS``). ``multi_tenant`` is deliberately
    not consulted: sniffing a loopback channel requires being on the machine,
    which is the same-principal story regardless of how many tenants the
    product serves.
    """
    return bool(
        model.relaxes_remote()
        and req in _TRANSPORT_REQS
        and _TRANSPORT_PATTERN.search(prose)
        and not _OUTBOUND_PATTERN.search(prose)
    )


def matched_rule(finding: dict, model: TrustModel) -> str | None:
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
    if _topology_rule_applies(model, req):
        return "single_host_topology"
    if _loopback_transport_rule_applies(model, req, prose):
        return "loopback_transport"
    return None
