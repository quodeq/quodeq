"""Deterministic provenance gate for the critical-severity bar (issue #639).

The prompt-level gate in ``evaluation_rules.md`` asks the model not to mark an
unguarded-access (R-FT-2) or path-from-string (S-AUT-3) finding ``critical``
unless a reachable EXTERNAL source is named. That gate is advisory. This module
enforces it deterministically at the finding sink: a critical R-FT-2/S-AUT-3
finding whose evidence names no external source is de-escalated to ``major``.

Generality (a hard requirement): the decision keys off TRUST-BOUNDARY SOURCE
CONCEPTS in the model's natural-language reason -- universal and language-
independent -- never code syntax (``sys.argv``) or project specifics. The
vocabulary is curated to SPECIFIC INGRESS CHANNELS and deliberately EXCLUDES:
  - rhetorical words that appear in false-positive reasons too ("attacker",
    "file", "untrusted", "caller"), and
  - the unguarded-access pattern's own words ("argument", "parameter", "param"),
    which would otherwise make an R-FT-2 FP look externally sourced.
"""
from __future__ import annotations

import logging
import re

_log = logging.getLogger(__name__)

# The standard requirement IDs whose critical bar depends on reachable input
# provenance: R-FT-2 (unguarded access) and S-AUT-3 (path/key from a value).
# Stable across all scans (they are ISO25010 standard IDs, not project-specific).
PROVENANCE_GATED_REQS: frozenset[str] = frozenset({"R-FT-2", "S-AUT-3"})

# Marker stamped on a finding the gate de-escalates (additive output field).
DOWNGRADE_MARKER = "provenance_downgrade"

# Language-neutral trust-boundary INGRESS-CHANNEL concepts. Matched as whole
# words/phrases. NEVER code syntax, never rhetoric, never the FP pattern's words.
EXTERNAL_SOURCE_TERMS: frozenset[str] = frozenset({
    # web / network ingress
    "request", "http request", "request body", "request header",
    "request parameter", "query string", "query parameter", "query param",
    "route param", "url param", "path parameter", "header", "response header",
    "http header", "cookie", "form data", "multipart", "payload", "post data",
    "webhook", "websocket", "grpc", "network request", "network input", "socket",
    # process / cli
    "command-line", "command line", "command-line argument", "cli argument",
    "cli arg", "argv",
    # environment
    "environment variable", "env var",
    # io / ipc
    "stdin", "standard input", "upload", "uploaded file", "file upload",
    "message queue", "queue message",
    # explicit untrusted-user phrasing
    "user input", "user-supplied", "user-controlled", "user-provided",
})

# Whole-word/phrase pattern; longer phrases first so they win in the alternation.
# Trailing ``s?`` tolerates plurals ("header" -> "headers") without enumerating
# every plural form.
_TERM_PATTERN = re.compile(
    "|".join(
        rf"\b{re.escape(term)}s?\b"
        for term in sorted(EXTERNAL_SOURCE_TERMS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


def names_external_source(text: str | None) -> bool:
    """True if *text* mentions any trust-boundary external ingress concept."""
    if not text:
        return False
    return _TERM_PATTERN.search(text) is not None


def apply_provenance_gate(finding: dict) -> bool:
    """De-escalate a critical R-FT-2/S-AUT-3 finding that names no external
    source to ``major``, in place. Returns True iff it downgraded.

    Only touches violations at ``critical`` for the gated reqs; everything else
    (other reqs, ``major``/``minor``, compliance) is left untouched. Never drops.
    Detection reads the model's prose (``reason`` + title ``w``) only, so it is
    language-independent; the code ``snippet`` is intentionally not consulted.
    """
    if finding.get("t") != "violation":
        return False
    if finding.get("req") not in PROVENANCE_GATED_REQS:
        return False
    if finding.get("severity") != "critical":
        return False
    haystack = " ".join(str(finding.get(k) or "") for k in ("reason", "w"))
    if names_external_source(haystack):
        return False
    finding["severity"] = "major"
    finding[DOWNGRADE_MARKER] = True
    _log.debug(
        "provenance gate: downgraded %s finding to major (no external source named): %s",
        finding.get("req"), finding.get("file"),
    )
    return True
