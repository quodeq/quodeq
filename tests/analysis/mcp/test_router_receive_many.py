"""FindingsRouter.receive_many: one PrecedentCorpus.match_many call for a
batch of findings from one file (finding 5598)."""
from __future__ import annotations

import io
import json
from pathlib import Path

from quodeq.analysis.mcp.enricher import CompiledContext
from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.context.precedent import PrecedentCorpus


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


# --- The batch path must score the ENRICHED snippet -------------------------
# The corpus is built from enriched snippets, so embedding the model's raw
# quote scores a different text than the per-finding path and a dismissed
# precedent stops downweighting.

_MODEL_QUOTE = "password = os.environ['PW']  # as the model quoted it"


def _source(tmp_path: Path) -> Path:
    src = tmp_path / "auth.py"
    src.write_text("\n".join(f"source line {i}" for i in range(1, 21)))
    return src


def _matching_corpus(tmp_path: Path, marker: str) -> tuple[PrecedentCorpus, list[str]]:
    """Corpus that only matches texts containing *marker*, plus the embed log."""
    embedded: list[str] = []

    def embed(texts: list[str]) -> list[list[float]]:
        embedded.extend(texts)
        return [[1.0, 0.0] if marker in t else [0.0, 1.0] for t in texts]

    corpus = PrecedentCorpus(
        vectors=[[1.0, 0.0]], embed=embed, threshold=0.85,
        marker_path=tmp_path / ".precedent_marker",
    )
    return corpus, embedded


def _enriching_router(tmp_path: Path, corpus: PrecedentCorpus) -> FindingsRouter:
    ctx = CompiledContext(precedent_fingerprints=set())
    ctx.work_dir = tmp_path
    ctx.precedent_corpus = corpus
    return FindingsRouter(io.StringIO(), context=ctx)


def test_receive_many_embeds_the_enriched_snippet_not_the_model_quote(tmp_path) -> None:
    _source(tmp_path)
    corpus, embedded = _matching_corpus(tmp_path, "source line 10")
    router = _enriching_router(tmp_path, corpus)

    router.receive_many([_violation("S-CON-1", "auth.py", 10, _MODEL_QUOTE)])

    assert len(embedded) == 1
    assert "source line 10" in embedded[0]
    assert _MODEL_QUOTE not in embedded[0]


def test_receive_many_downweights_a_precedent_exactly_like_receive(tmp_path) -> None:
    _source(tmp_path)
    args = _violation("S-CON-1", "auth.py", 10, _MODEL_QUOTE)

    batch_corpus, _ = _matching_corpus(tmp_path, "source line 10")
    batched = _enriching_router(tmp_path, batch_corpus).receive_many([dict(args)])

    single_corpus, _ = _matching_corpus(tmp_path, "source line 10")
    single_router = _enriching_router(tmp_path, single_corpus)
    single_router.receive(dict(args))
    written = json.loads(single_router._fh.getvalue().splitlines()[0])

    assert batched[0]["confidence"] == written["confidence"] == 25
