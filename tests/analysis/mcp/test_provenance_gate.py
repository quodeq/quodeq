"""Tests for the deterministic provenance gate (issue #639)."""
from __future__ import annotations

import pytest

from quodeq.analysis.mcp.provenance_gate import (
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
    assert f["provenance_downgrade"] is True


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
    assert "provenance_downgrade" not in f


def test_ignores_non_gated_req():
    f = _finding(req="S-CON-1", severity="critical", reason="hardcoded secret in source")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "critical"


def test_ignores_non_critical_severity():
    f = _finding(req="R-FT-2", severity="major", reason="builds a path from the key")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "major"
    assert "provenance_downgrade" not in f


def test_ignores_compliance():
    f = _finding(t="compliance", req="S-AUT-3", severity="critical", reason="validated path")
    assert apply_provenance_gate(f) is False
    assert f["severity"] == "critical"


def test_gated_reqs_are_the_two_patterns():
    assert PROVENANCE_GATED_REQS == frozenset({"R-FT-2", "S-AUT-3"})
