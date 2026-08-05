"""The one place every deterministic severity gate is applied to a finding.

Quodeq has two gates, and they must run together, in one order, at every sink
that produces a finding. Enforcing that by convention has failed twice:

* issue #657 -- cache replay wrote findings without ``apply_provenance_gate``,
  so a stale critical replayed at critical and inflated the grade.
* the trust-model work -- the same replay path was then missing
  ``apply_scope_gate`` for the same reason, and needed the same fix again.

Both were one shape: a code path nobody enumerated. Three sinks exist today --
``FindingEnricher.enrich`` (live), ``_write_findings`` (cache replay) and
``checks.runner`` (deterministic checkers) -- and the only thing that stopped
the third from being a third instance of that bug was that no shipped standard
declares a ``check`` on a gated requirement yet.

So the sequence lives here rather than at the call sites. A fourth sink gets
the gates by calling one function, and a new gate is added in one place instead
of three. Callers are responsible only for resolving the :class:`TrustModel`
(once, not per finding) and calling this.

ORDER IS LOAD-BEARING, which is the other reason not to leave this to callers:
``apply_provenance_gate`` can rewrite ``critical`` -> ``major``, and
``apply_scope_gate`` only ever looks at ``major``. Run scope first and a
critical the provenance gate was about to demote never becomes eligible for
the scope gate at all, so a finding that should end at ``minor`` stops at
``major``. The gates are deliberately split at that severity boundary (see
``apply_scope_gate``'s docstring) precisely so this order is the only correct
one.
"""
from __future__ import annotations

from quodeq.analysis.mcp.provenance_gate import apply_provenance_gate
from quodeq.analysis.mcp.scope_gate import apply_scope_gate
from quodeq.context.trust_model import TrustModel


def apply_severity_gates(finding: dict, trust_model: TrustModel | None) -> bool:
    """Apply every severity gate to *finding*, in place. True iff one fired.

    *finding* is the short-key wire dict (``t``, ``req``, ``severity``,
    ``reason``, ``w``) every sink already speaks. *trust_model* may be ``None``,
    which no-ops the scope gate -- the honest value for a caller that has no
    project root to resolve one from.

    Neither gate ever drops a finding or raises on a well-formed dict; both are
    no-ops on anything they do not recognise, so calling this on an already
    gated finding (as cache replay does) is safe.
    """
    downgraded = apply_provenance_gate(finding)
    # Not ``or``-shortcircuited: the scope gate must run even when the
    # provenance gate already fired, because that is exactly the critical ->
    # major -> minor case this order exists to allow.
    if apply_scope_gate(finding, trust_model):
        downgraded = True
    return downgraded
