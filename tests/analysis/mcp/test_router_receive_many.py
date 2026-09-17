"""FindingsRouter.receive_many: one PrecedentCorpus.match_many call for a
batch of findings from one file (finding 5598)."""
from __future__ import annotations

import io
import json

from quodeq.analysis.mcp.enricher import CompiledContext
from quodeq.analysis.mcp.router import FindingsRouter


class _FakeCorpus:
    def __init__(self, score: float | None, threshold: float = 0.85) -> None:
        self._score = score
        self.threshold = threshold
        self.calls: list[list[str]] = []

    def match_many(self, texts: list[str]) -> list[float | None]:
        self.calls.append(list(texts))
        return [self._score for _ in texts]

    def match(self, text: str) -> float | None:
        raise AssertionError("match() called instead of the batch match_many()")


def _violation(req: str, file: str, line: int, snippet: str) -> dict:
    return {
        "t": "violation", "req": req, "file": file, "line": line,
        "reason": "hardcoded secret", "snippet": snippet,
    }


def test_receive_many_calls_the_corpus_once_per_batch() -> None:
    corpus = _FakeCorpus(score=0.91)
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = corpus
    fh = io.StringIO()
    router = FindingsRouter(fh, context=ctx, file_reader=lambda p: "")

    findings = [
        _violation("S-CON-1", "auth.py", 10, "password = 'a'"),
        _violation("S-CON-2", "auth.py", 20, "password = 'b'"),
        _violation("S-CON-3", "auth.py", 30, "password = 'c'"),
    ]

    results = router.receive_many(findings)

    assert len(corpus.calls) == 1
    assert len(corpus.calls[0]) == 3
    assert len(results) == 3
    assert all(f["confidence"] == 25 for f in results)

    written = [json.loads(ln) for ln in fh.getvalue().splitlines()]
    assert len(written) == 3
    assert all(f["confidence"] == 25 for f in written)


def test_receive_many_dedupes_within_the_batch() -> None:
    corpus = _FakeCorpus(score=0.91)
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.precedent_corpus = corpus
    fh = io.StringIO()
    router = FindingsRouter(fh, context=ctx, file_reader=lambda p: "")

    dup = _violation("S-CON-1", "auth.py", 10, "password = 'a'")
    findings = [dup, dict(dup)]

    results = router.receive_many(findings)

    assert len(results) == 1
    assert len(corpus.calls) == 1 and len(corpus.calls[0]) == 1


def test_receive_many_without_corpus_still_writes_findings() -> None:
    ctx = CompiledContext(precedent_fingerprints=set())
    fh = io.StringIO()
    router = FindingsRouter(fh, context=ctx, file_reader=lambda p: "")

    findings = [_violation("S-CON-1", "auth.py", 10, "password = 'a'")]
    results = router.receive_many(findings)

    assert len(results) == 1
    assert "confidence" not in results[0] or results[0]["confidence"] == 100


def test_receive_many_empty_batch_is_a_noop() -> None:
    ctx = CompiledContext(precedent_fingerprints=set())
    fh = io.StringIO()
    router = FindingsRouter(fh, context=ctx, file_reader=lambda p: "")

    assert router.receive_many([]) == []
    assert fh.getvalue() == ""
    assert router.counter == 0
