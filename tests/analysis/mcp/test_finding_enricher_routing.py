"""Tests for FindingEnricher: dedup keys, dimension rerouting, file-read caching, vt_raw."""
from __future__ import annotations

from quodeq.analysis.mcp.enricher import (
    CompiledContext,
    FindingEnricher,
)

from ._finding_enricher_helpers import _enricher


# ---------------------------------------------------------------------------
# dedup_key
# ---------------------------------------------------------------------------

def test_dedup_key_resolves_principle_from_reqs() -> None:
    reqs = {"S-CON-1": {"principle": "Confidentiality", "text": "..."}}
    key = _enricher(compiled_reqs=reqs).dedup_key(
        {"req": "S-CON-1", "file": "a.py", "line": 1, "t": "violation"}
    )
    assert key == ("Confidentiality", "a.py", 1, "violation")


def test_dedup_key_uses_explicit_principle() -> None:
    key = _enricher().dedup_key(
        {"p": "Custom", "file": "a.py", "line": 1, "t": "violation"}
    )
    assert key[0] == "Custom"


# ---------------------------------------------------------------------------
# Dimension/requirement agreement gate (#661)
# ---------------------------------------------------------------------------

def test_reroutes_finding_to_requirement_dimension() -> None:
    """The requirement is authoritative: a finding the model declared under
    one dimension is rerouted to the dimension its requirement belongs to
    (multi-dimension scans populate req_to_dim across standards)."""
    req_to_dim = {"S-CON-1": "security"}
    result = _enricher(req_to_dim=req_to_dim).enrich(
        {"t": "violation", "req": "S-CON-1", "d": "maintainability",
         "severity": "critical", "file": "a.py", "line": 1}
    )
    assert result["d"] == "security"


def test_does_not_reroute_correctly_filed_finding() -> None:
    req_to_dim = {"M-MOD-1": "maintainability"}
    result = _enricher(req_to_dim=req_to_dim).enrich(
        {"t": "violation", "req": "M-MOD-1", "d": "maintainability",
         "file": "a.py", "line": 1}
    )
    assert result["d"] == "maintainability"


def test_keeps_declared_dimension_when_requirement_unresolvable() -> None:
    """Single-dimension scans leave req_to_dim empty; an unresolvable req
    cannot be rerouted, so the declared dimension is preserved (the unmapped
    finding is quarantined downstream at principle grouping, not here)."""
    result = _enricher(dimension="maintainability").enrich(
        {"t": "violation", "req": "N/A", "d": "maintainability",
         "severity": "critical", "file": "a.py", "line": 1}
    )
    assert result["d"] == "maintainability"


def test_reroute_is_logged() -> None:
    captured: list[str] = []

    class _CapturingLog:
        def info(self, message: str) -> None: pass
        def warning(self, message: str) -> None: captured.append(message)
        def debug(self, message: str) -> None: pass
        def error(self, message: str) -> None: pass

    req_to_dim = {"S-CON-1": "security"}
    FindingEnricher(CompiledContext(req_to_dim=req_to_dim), log=_CapturingLog()).enrich(
        {"t": "violation", "req": "S-CON-1", "d": "maintainability",
         "severity": "critical", "file": "a.py", "line": 1}
    )
    assert any("security" in m and "maintainability" in m for m in captured)


def test_read_file_is_cached_across_findings_in_the_same_file(tmp_path) -> None:
    src = tmp_path / "a.py"
    src.write_text("line1\nline2\nline3\n", encoding="utf-8")

    read_calls = {"n": 0}

    def counting_reader(path):
        read_calls["n"] += 1
        return path.read_text(encoding="utf-8")

    context = CompiledContext(work_dir=tmp_path)
    enricher = FindingEnricher(context, counting_reader)

    enricher.enrich({"p": "P1", "t": "violation", "d": "perf", "file": "a.py", "line": 1})
    enricher.enrich({"p": "P1", "t": "violation", "d": "perf", "file": "a.py", "line": 2})
    enricher.enrich({"p": "P1", "t": "violation", "d": "perf", "file": "a.py", "line": 3})

    assert read_calls["n"] == 1, f"expected 1 read for 3 findings in the same file, got {read_calls['n']}"


# ---------------------------------------------------------------------------
# Raw violation-type tag (taxonomy spec 2026-09-15, PR A)
# ---------------------------------------------------------------------------

def test_stamps_vt_raw_from_model_tag() -> None:
    result = _enricher().enrich({"t": "violation", "req": "R-FT-1", "vt": "Empty_Catch"})
    assert result["vt"] == "Empty_Catch"  # PR A leaves the scoring key untouched
    assert result["vt_raw"] == "Empty_Catch"


def test_no_vt_raw_without_model_tag() -> None:
    result = _enricher().enrich({"t": "violation", "req": "R-FT-1"})
    assert "vt_raw" not in result
