"""Tests for FindingEnricher — pure dict transformation, no file I/O."""
from __future__ import annotations

from quodeq.analysis.mcp.enricher import (
    CompiledContext,
    FindingEnricher,
)
from quodeq.context.project_shape import Deployment, ProjectShape
from quodeq.context.precedent import fingerprint as make_fingerprint


def _enricher(**ctx_kwargs) -> FindingEnricher:
    return FindingEnricher(CompiledContext(**ctx_kwargs))


# ---------------------------------------------------------------------------
# Standards enrichment
# ---------------------------------------------------------------------------

def test_fills_req_refs_from_compiled_refs() -> None:
    refs = {"S-CON-1": [{"label": "CWE-798", "url": "https://example.com"}]}
    result = _enricher(compiled_refs=refs).enrich(
        {"p": "Confidentiality", "t": "violation", "d": "security", "req": "S-CON-1"}
    )
    assert result["req_refs"] == [{"label": "CWE-798", "url": "https://example.com"}]


def test_no_req_refs_without_matching_req() -> None:
    refs = {"S-CON-1": [{"label": "CWE-798", "url": "https://example.com"}]}
    result = _enricher(compiled_refs=refs).enrich(
        {"p": "P1", "t": "violation", "d": "perf", "req": "UNKNOWN-1"}
    )
    assert "req_refs" not in result


def test_fills_principle_from_compiled_reqs() -> None:
    reqs = {"S-CON-1": {"principle": "Confidentiality", "text": "..."}}
    result = _enricher(compiled_reqs=reqs).enrich({"t": "violation", "req": "S-CON-1"})
    assert result["p"] == "Confidentiality"


def test_does_not_overwrite_explicit_principle() -> None:
    reqs = {"S-CON-1": {"principle": "Confidentiality", "text": "..."}}
    result = _enricher(compiled_reqs=reqs).enrich(
        {"p": "Custom", "t": "violation", "req": "S-CON-1"}
    )
    assert result["p"] == "Custom"


def test_fills_dimension_from_req_to_dim() -> None:
    req_to_dim = {"S-CON-1": "security"}
    result = _enricher(req_to_dim=req_to_dim).enrich(
        {"t": "violation", "req": "S-CON-1"}
    )
    assert result["d"] == "security"


def test_fills_dimension_from_fallback() -> None:
    result = _enricher(dimension="maintainability").enrich(
        {"t": "violation", "req": "M-MOD-1"}
    )
    assert result["d"] == "maintainability"


def test_schema_version_always_set() -> None:
    result = _enricher().enrich({"p": "P1", "t": "violation"})
    assert result["schema_version"] == 1


# ---------------------------------------------------------------------------
# Path-role downweight
# ---------------------------------------------------------------------------

def test_violation_on_test_file_downweighted_to_50() -> None:
    result = _enricher().enrich(
        {"p": "P1", "t": "violation", "file": "tests/test_server.py", "line": 1}
    )
    assert result["confidence"] == 50


def test_violation_on_prod_path_not_downweighted() -> None:
    result = _enricher().enrich(
        {"p": "P1", "t": "violation", "file": "src/server.py", "line": 1}
    )
    assert "confidence" not in result


def test_compliance_not_downweighted_by_path_role() -> None:
    result = _enricher().enrich(
        {"p": "P1", "t": "compliance", "file": "tests/test_server.py", "line": 1}
    )
    assert "confidence" not in result


def test_llm_low_confidence_preserved_over_path_role() -> None:
    result = _enricher().enrich(
        {"p": "P1", "t": "violation", "file": "tests/test_server.py", "line": 1, "confidence": 25}
    )
    assert result["confidence"] == 25


# ---------------------------------------------------------------------------
# Shape downweight
# ---------------------------------------------------------------------------

def test_hosted_service_finding_downweighted_on_desktop() -> None:
    shape = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)
    result = _enricher(project_shape=shape).enrich({
        "p": "P1", "t": "violation",
        "w": "Concurrent callers can corrupt shared state",
        "reason": "Multiple concurrent callers will race.",
        "file": "src/main.py", "line": 5,
    })
    assert result["confidence"] == 40


def test_unrelated_finding_not_shape_downweighted() -> None:
    shape = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)
    result = _enricher(project_shape=shape).enrich({
        "p": "P1", "t": "violation",
        "w": "Quadratic loop", "reason": "Nested for-loops over the same list.",
        "file": "src/main.py", "line": 5,
    })
    assert "confidence" not in result


def test_web_service_finding_not_shape_downweighted() -> None:
    shape = ProjectShape(deployment=Deployment.WEB_SERVICE, is_single_user=False)
    result = _enricher(project_shape=shape).enrich({
        "p": "P1", "t": "violation",
        "w": "Concurrent callers can corrupt shared state",
        "reason": "Multiple concurrent callers will race.",
        "file": "src/main.py", "line": 5,
    })
    assert "confidence" not in result


# ---------------------------------------------------------------------------
# Precedent downweight
# ---------------------------------------------------------------------------

def test_precedent_match_downweighted_to_25() -> None:
    snippet = "password = 'hunter2'"
    fp = make_fingerprint("S-CON-1", snippet)
    result = _enricher(precedent_fingerprints={fp}).enrich({
        "p": "Confidentiality", "t": "violation", "req": "S-CON-1",
        "w": "Hardcoded credential", "snippet": snippet,
        "file": "src/main.py", "line": 5,
    })
    assert result["confidence"] == 25


def test_precedent_miss_not_downweighted() -> None:
    result = _enricher(precedent_fingerprints={"other-fp"}).enrich({
        "p": "P1", "t": "violation", "req": "S-CON-1",
        "snippet": "password = 'hunter2'", "file": "src/main.py", "line": 5,
    })
    assert "confidence" not in result


def test_precedent_does_not_downweight_compliance() -> None:
    snippet = "password = 'hunter2'"
    fp = make_fingerprint("S-CON-1", snippet)
    result = _enricher(precedent_fingerprints={fp}).enrich({
        "p": "P1", "t": "compliance", "req": "S-CON-1",
        "snippet": snippet, "file": "src/main.py", "line": 5,
    })
    assert "confidence" not in result


def test_precedent_respects_llm_emitted_confidence() -> None:
    snippet = "password = 'hunter2'"
    fp = make_fingerprint("S-CON-1", snippet)
    result = _enricher(precedent_fingerprints={fp}).enrich({
        "p": "P1", "t": "violation", "req": "S-CON-1",
        "snippet": snippet, "file": "src/main.py", "line": 5, "confidence": 60,
    })
    assert result["confidence"] == 60


# ---------------------------------------------------------------------------
# Semantic precedent tier
# ---------------------------------------------------------------------------

class _FakeCorpus:
    def __init__(self, score: float | None, threshold: float = 0.85) -> None:
        self._score = score
        self.threshold = threshold
        self.calls: list[str] = []

    def match(self, text: str) -> float | None:
        self.calls.append(text)
        return self._score


def _violation_args(**over):
    args = {
        "t": "violation", "req": "S-CON-1", "file": "auth.py", "line": 42,
        "reason": "hardcoded secret", "snippet": "password = 'secret'",
    }
    args.update(over)
    return args


def test_semantic_match_downweights_on_exact_miss() -> None:
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = _FakeCorpus(score=0.91)
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    finding = enricher.enrich(_violation_args())
    assert finding["confidence"] == 25


def test_semantic_below_threshold_keeps_confidence() -> None:
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = _FakeCorpus(score=0.5)
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    finding = enricher.enrich(_violation_args())
    assert "confidence" not in finding or finding["confidence"] == 100


def test_semantic_skipped_when_exact_matches() -> None:
    fp = make_fingerprint("S-CON-1", "password = 'secret'")
    corpus = _FakeCorpus(score=0.99)
    ctx = CompiledContext(precedent_fingerprints={fp})
    ctx.precedent_corpus = corpus
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    finding = enricher.enrich(_violation_args())
    assert finding["confidence"] == 25
    assert corpus.calls == []  # exact tier won; no embed call spent


def test_semantic_skips_scope_level_findings() -> None:
    corpus = _FakeCorpus(score=0.99)
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = corpus
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    enricher.enrich(_violation_args(line=0))
    enricher.enrich(_violation_args(scope="file"))
    enricher.enrich(_violation_args(snippet=""))
    assert corpus.calls == []


def test_semantic_none_score_keeps_confidence() -> None:
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = _FakeCorpus(score=None)
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    finding = enricher.enrich(_violation_args())
    assert "confidence" not in finding or finding["confidence"] == 100


def test_semantic_score_equal_to_threshold_matches() -> None:
    """The comparison is `score >= threshold`; an exact tie must still match."""
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = _FakeCorpus(score=0.85, threshold=0.85)
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    finding = enricher.enrich(_violation_args())
    assert finding["confidence"] == 25


def test_semantic_respects_llm_emitted_confidence() -> None:
    """Mirrors test_precedent_respects_llm_emitted_confidence for the exact
    tier: the downweight guard only fires on None/100, so a pre-set
    confidence survives a high-scoring semantic match too."""
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = _FakeCorpus(score=0.99)
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    finding = enricher.enrich(_violation_args(confidence=50))
    assert finding["confidence"] == 50


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


def test_reroute_is_logged(caplog) -> None:
    import logging
    req_to_dim = {"S-CON-1": "security"}
    with caplog.at_level(logging.WARNING):
        _enricher(req_to_dim=req_to_dim).enrich(
            {"t": "violation", "req": "S-CON-1", "d": "maintainability",
             "severity": "critical", "file": "a.py", "line": 1}
        )
    assert any(
        "security" in r.getMessage() and "maintainability" in r.getMessage()
        for r in caplog.records
    )
