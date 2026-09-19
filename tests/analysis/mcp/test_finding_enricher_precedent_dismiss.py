"""The enricher hands an EXACT precedent match to ``on_precedent_match`` (#1208).

Only the exact tier: a semantic match is a guess and stays a UI signal.
The hook must never break enrichment.
"""
from __future__ import annotations

from quodeq.context.precedent import fingerprint as make_fingerprint

from tests.analysis.mcp._finding_enricher_helpers import _enricher

SNIPPET = "password = 'hunter2'"
FP = make_fingerprint("S-CON-1", SNIPPET)


def _args(t: str = "violation", snippet: str = SNIPPET) -> dict:
    return {
        "p": "Confidentiality", "t": t, "req": "S-CON-1",
        "w": "Hardcoded credential", "snippet": snippet,
        "file": "src/main.py", "line": 5,
    }


def test_exact_match_reaches_the_hook_with_the_enriched_finding() -> None:
    seen: list[dict] = []
    result = _enricher(precedent_fingerprints={FP}, on_precedent_match=seen.append).enrich(_args())
    assert seen == [result]
    assert result["confidence"] == 25


def test_miss_does_not_reach_the_hook() -> None:
    seen: list[dict] = []
    _enricher(precedent_fingerprints={"other"}, on_precedent_match=seen.append).enrich(_args())
    assert seen == []


def test_compliance_does_not_reach_the_hook() -> None:
    seen: list[dict] = []
    _enricher(precedent_fingerprints={FP}, on_precedent_match=seen.append).enrich(_args(t="compliance"))
    assert seen == []


def test_semantic_match_does_not_reach_the_hook() -> None:
    class Corpus:
        threshold = 0.5

        def match(self, _text: str) -> float:
            return 0.99

        def match_many(self, texts: list[str]) -> list[float]:
            return [0.99] * len(texts)

    seen: list[dict] = []
    result = _enricher(
        precedent_fingerprints={"other"}, precedent_corpus=Corpus(), on_precedent_match=seen.append,
    ).enrich(_args())
    assert result["confidence"] == 25
    assert seen == []


def test_hook_failure_never_breaks_enrichment() -> None:
    def boom(_finding: dict) -> None:
        raise PermissionError("actions.jsonl unwritable")

    result = _enricher(precedent_fingerprints={FP}, on_precedent_match=boom).enrich(_args())
    assert result["confidence"] == 25


def test_enrich_many_uses_the_hook_too() -> None:
    seen: list[dict] = []
    results = _enricher(precedent_fingerprints={FP}, on_precedent_match=seen.append).enrich_many([_args(), _args(snippet="x = 1")])
    assert seen == [results[0]]
