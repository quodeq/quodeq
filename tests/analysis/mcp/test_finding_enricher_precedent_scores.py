"""FindingEnricher.precedent_scores: one PrecedentCorpus.match_many call for
a batch of findings (finding 5598). Split from test_finding_enricher.py to
stay under the file-size ratchet (that file is already over the 240-line
sibling-file threshold)."""
from __future__ import annotations

import pytest

from quodeq.analysis.mcp.enricher import CompiledContext, FindingEnricher
from quodeq.context.precedent import fingerprint as make_fingerprint, precedent_text


class _FakeCorpus:
    """A corpus stub keyed by exact lookup text, batch-only.

    ``match`` raises: any test that reaches it proves the code under test
    fell back to the old per-finding call instead of the batch path.
    """

    def __init__(self, scores_by_text: dict[str, float], threshold: float = 0.85) -> None:
        self._scores_by_text = scores_by_text
        self.threshold = threshold
        self.calls: list[list[str]] = []

    def match_many(self, texts: list[str]) -> list[float | None]:
        self.calls.append(list(texts))
        return [self._scores_by_text.get(t) for t in texts]

    def match(self, text: str) -> float | None:
        raise AssertionError("match() called instead of the batch match_many()")


def _violation(req: str, snippet: str, **over) -> dict:
    args = {
        "t": "violation", "req": req, "file": "auth.py", "line": 42,
        "reason": "hardcoded secret", "snippet": snippet,
    }
    args.update(over)
    return args


def test_precedent_scores_embeds_eligible_findings_in_one_call() -> None:
    f1 = _violation("S-CON-1", "password = 'a'")
    f2 = _violation("S-CON-2", "password = 'b'")
    text1 = precedent_text(f1["req"], f1["snippet"])
    text2 = precedent_text(f2["req"], f2["snippet"])

    corpus = _FakeCorpus({text1: 0.91, text2: 0.5})
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = corpus
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")

    scores = enricher.precedent_scores([f1, f2])

    assert len(corpus.calls) == 1
    assert corpus.calls[0] == [text1, text2]
    assert scores == [pytest.approx(0.91), pytest.approx(0.5)]


def test_precedent_scores_skips_exact_matched_and_ineligible_findings() -> None:
    matched_snippet = "password = 'hunter2'"
    fp = make_fingerprint("S-CON-1", matched_snippet)
    exact = _violation("S-CON-1", matched_snippet)  # already an exact dismissal
    scope_level = _violation("S-CON-2", "irrelevant", scope="file")
    eligible = _violation("S-CON-3", "password = 'c'")
    text_eligible = precedent_text(eligible["req"], eligible["snippet"])

    corpus = _FakeCorpus({text_eligible: 0.9})
    ctx = CompiledContext(precedent_fingerprints={fp})
    ctx.precedent_corpus = corpus
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")

    scores = enricher.precedent_scores([exact, scope_level, eligible])

    assert corpus.calls == [[text_eligible]]
    assert scores == [None, None, pytest.approx(0.9)]


def test_precedent_scores_without_corpus_returns_all_none() -> None:
    ctx = CompiledContext(precedent_fingerprints=set())
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")
    findings = [_violation("S-CON-1", "password = 'a'"), _violation("S-CON-2", "password = 'b'")]

    assert enricher.precedent_scores(findings) == [None, None]


def test_enrich_uses_supplied_precedent_score_without_calling_corpus() -> None:
    corpus = _FakeCorpus({})
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = corpus
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")

    finding = enricher.enrich(_violation("S-CON-1", "password = 'a'"), precedent_score=0.99)

    assert finding["confidence"] == 25
    assert corpus.calls == []


def test_enrich_supplied_none_score_keeps_full_confidence() -> None:
    corpus = _FakeCorpus({})
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = corpus
    enricher = FindingEnricher(ctx, file_reader=lambda p: "")

    finding = enricher.enrich(_violation("S-CON-1", "password = 'a'"), precedent_score=None)

    assert "confidence" not in finding or finding["confidence"] == 100
    assert corpus.calls == []
