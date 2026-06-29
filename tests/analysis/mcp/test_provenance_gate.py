"""Tests for the deterministic provenance gate (issue #639)."""
from __future__ import annotations

import pytest

from quodeq.analysis.mcp.enricher import CompiledContext, FindingEnricher
from quodeq.analysis.mcp.provenance_gate import (
    DOWNGRADE_MARKER,
    EXTERNAL_SOURCE_TERMS,
    PROVENANCE_GATED_REQS,
    apply_provenance_gate,
    names_external_source,
)

# Reasons that DO name a reachable external source -> external.
_EXTERNAL_REASONS = [
    "The filename is read from the inbound HTTP request and never validated.",
    "Value comes straight from a query parameter with no sanitisation.",
    "Dereferences the x-active-users response header which may be absent.",
    "Path built from a command-line argument supplied by the caller.",
    "Reads the destination from an environment variable.",
    "The uploaded file name flows into the path unchecked.",
    "Splits a value taken from request body JSON.",
    "Reads a cookie value and uses it as a key.",
]

# Reasons that name NO external source (internal value, or only rhetoric) ->
# must NOT count as external. These include the real fa56db32 FP phrasings,
# which use "attacker" and "file access" rhetorically and say "argument".
_INTERNAL_REASONS = [
    "Constructs a path from slices of the 'key' string without validating that "
    "the key does not contain traversal sequences. This allows an attacker to "
    "provide a crafted key leading to unauthorized file access.",
    "The function argument is dereferenced without a null guard and could throw.",
    "Spreads the thresholds prop without checking it is defined first.",
    "Destructures the hook options object; a missing field would be undefined.",
    "Uses a SHA-256 content hash to build the cache directory path.",
    "Opens a path built from a hardcoded constant.",
]


@pytest.mark.parametrize("reason", _EXTERNAL_REASONS)
def test_external_reasons_detected(reason):
    assert names_external_source(reason) is True


@pytest.mark.parametrize("reason", _INTERNAL_REASONS)
def test_internal_reasons_not_detected(reason):
    assert names_external_source(reason) is False


def test_empty_text_is_not_external():
    assert names_external_source("") is False
    assert names_external_source(None) is False  # type: ignore[arg-type]


def test_match_is_case_insensitive():
    assert names_external_source("Reads the HTTP REQUEST body") is True


def test_rhetoric_words_are_not_in_vocabulary():
    # These appear in false-positive reasons and must not be treated as sources.
    for forbidden in ("attacker", "file", "argument", "parameter", "untrusted", "caller"):
        assert forbidden not in EXTERNAL_SOURCE_TERMS


def _finding(**kw) -> dict:
    base = {"t": "violation", "req": "S-AUT-3", "severity": "critical",
            "w": "Path traversal", "reason": "builds a path from the key"}
    base.update(kw)
    return base


def test_downgrades_critical_internal_to_major():
    f = _finding(req="S-AUT-3", reason="builds a path from a SHA-256 cache key")
    assert apply_provenance_gate(f) is True
    assert f["severity"] == "major"
    assert f[DOWNGRADE_MARKER] is True


def test_downgrades_real_fa56db32_cache_fp():
    f = _finding(req="S-AUT-3", reason=_INTERNAL_REASONS[0])  # the "attacker/file" reason
    assert apply_provenance_gate(f) is True
    assert f["severity"] == "major"


def test_downgrades_unguarded_arg_fp():
    f = _finding(req="R-FT-2", reason="the function argument is dereferenced without a guard")
    assert apply_provenance_gate(f) is True
    assert f["severity"] == "major"


def test_keeps_critical_when_external_source_named():
    f = _finding(req="S-AUT-3", reason="path built from the HTTP request filename")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "critical"
    assert DOWNGRADE_MARKER not in f


def test_ignores_non_gated_req():
    f = _finding(req="S-CON-1", severity="critical", reason="hardcoded secret in source")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "critical"


def test_ignores_non_critical_severity():
    f = _finding(req="R-FT-2", severity="major", reason="builds a path from the key")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "major"
    assert DOWNGRADE_MARKER not in f


def test_ignores_compliance():
    f = _finding(t="compliance", req="S-AUT-3", severity="critical", reason="validated path")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "critical"


def test_gated_reqs_are_the_two_patterns():
    assert PROVENANCE_GATED_REQS == frozenset({"R-FT-2", "S-AUT-3"})


def test_plural_sources_detected():
    assert names_external_source("query parameters were not validated") is True
    assert names_external_source("reads multiple HTTP headers") is True


# ---------------------------------------------------------------------------
# Integration tests: gate wired into FindingEnricher.enrich (issue #639)
# ---------------------------------------------------------------------------

def _enrich(args: dict) -> dict:
    return FindingEnricher(CompiledContext()).enrich(args)


def test_enrich_downgrades_internal_critical():
    result = _enrich({
        "t": "violation", "req": "S-AUT-3", "severity": "critical",
        "file": "src/cache/local.py", "line": 59, "w": "Path traversal",
        "reason": "builds a path from a SHA-256 cache key with no external input",
    })
    assert result["severity"] == "major"
    assert result["provenance_downgrade"] is True


def test_enrich_keeps_external_critical():
    result = _enrich({
        "t": "violation", "req": "S-AUT-3", "severity": "critical",
        "file": "src/server/download.py", "line": 10, "w": "Path traversal",
        "reason": "path built from the HTTP request filename, unvalidated",
    })
    assert result["severity"] == "critical"
    assert "provenance_downgrade" not in result


def test_downgraded_finding_retains_all_other_fields():
    """No-drop invariant: a downgrade mutates only severity (+marker), never
    removes the finding or its other fields."""
    f = _finding(
        req="S-AUT-3", file="src/cache/local.py", line=59,
        w="Path traversal", reason="builds a path from a SHA-256 cache key",
    )
    assert apply_provenance_gate(f) is True
    assert f["severity"] == "major"
    # every other field survives intact
    assert f["t"] == "violation"
    assert f["req"] == "S-AUT-3"
    assert f["file"] == "src/cache/local.py"
    assert f["line"] == 59
    assert f["w"] == "Path traversal"
    assert f["reason"] == "builds a path from a SHA-256 cache key"


def test_non_referential_source_word_intentionally_kept_critical():
    """KNOWN, INTENTIONAL conservative bias (pinned so a future vocab edit cannot
    silently change it): the gate keeps `critical` whenever a vocabulary term
    appears at all, even used non-referentially (here "header" inside "file
    header bytes"). The gate never tries to disambiguate prose; it only ever
    errs toward keeping critical, never toward an unjustified downgrade."""
    f = _finding(
        req="S-AUT-3",
        reason="splits the file header bytes, a 4-byte internal magic number",
    )
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "critical"
    assert "provenance_downgrade" not in f
