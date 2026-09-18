"""PrecedentCorpus: matching, circuit breaker, and the backfill pass."""
import math
from pathlib import Path

import pytest

from quodeq.context.precedent import (
    MARKER_NAME,
    PrecedentCorpus,
    VectorStoreFns,
    precedent_text,
)


def _unit(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec]


def test_backfill_scans_the_corpus_once_not_per_chunk(monkeypatch) -> None:
    """The missing list is computed once and each chunk sliced off it.

    Rescanning every fingerprint per chunk made the backfill quadratic in
    the corpus size. A dict that counts its own iterations proves one pass.
    """
    from quodeq.context.precedent_store import Embedder, _backfill_missing

    monkeypatch.setattr("quodeq.context.precedent_store._BACKFILL_CHUNK", 1)
    iterations = [0]

    class CountingTexts(dict):
        def __iter__(self):
            iterations[0] += 1
            return super().__iter__()

    texts = CountingTexts({"fp1": "t1", "fp2": "t2", "fp3": "t3"})
    inserted: list[str] = []
    batches: list[list[str]] = []

    def insert(conn, model, pairs) -> bool:
        inserted.extend(fp for fp, _ in pairs)
        return True

    def embed(batch, **kwargs):
        batches.append(list(batch))
        return [[1.0, 0.0] for _ in batch]

    store = VectorStoreFns(
        open_vector_store=lambda project_dir, model: None,
        load_vectors=lambda conn: [],
        insert_vectors=insert,
        stored_fingerprints=lambda conn: set(),
        try_claim_backfill=lambda conn: True,
        release_backfill_claim=lambda conn: None,
    )

    n = _backfill_missing(
        store, object(), texts, Embedder(model="m", embed_fn=embed, batch_timeout=None),
    )

    assert n == 3
    assert batches == [["t1"], ["t2"], ["t3"]]
    assert inserted == ["fp1", "fp2", "fp3"]
    assert iterations[0] == 1


def _corpus(tmp_path: Path, vectors, embed, threshold=0.85) -> PrecedentCorpus:
    return PrecedentCorpus(
        vectors=vectors, embed=embed, threshold=threshold,
        marker_path=tmp_path / MARKER_NAME,
    )


def test_precedent_text_symmetric_normalization() -> None:
    assert precedent_text("R-1", "x  =  1 ;") == "R-1\n\nx = 1"
    assert precedent_text(None, None) is None


def test_match_returns_best_cosine(tmp_path: Path) -> None:
    corpus = _corpus(
        tmp_path,
        vectors=[_unit([1.0, 0.0]), _unit([0.0, 1.0])],
        embed=lambda texts: [[0.9, 0.1]],
    )
    score = corpus.match("anything")
    assert score is not None and score == pytest.approx(0.9939, abs=1e-3)


def test_match_error_trips_breaker_and_writes_marker(tmp_path: Path) -> None:
    def boom(texts):
        raise RuntimeError("embedder down")
    corpus = _corpus(tmp_path, vectors=[_unit([1.0, 0.0])], embed=boom)
    assert corpus.match("t") is None
    assert (tmp_path / MARKER_NAME).exists()
    # Subsequent calls short-circuit without calling the embedder.
    assert corpus.match("t") is None


def test_match_dims_mismatch_is_caught(tmp_path: Path) -> None:
    corpus = _corpus(
        tmp_path,
        vectors=[_unit([1.0, 0.0])],
        embed=lambda texts: [[1.0, 0.0, 0.0]],  # 3 dims vs stored 2
    )
    assert corpus.match("t") is None
    assert (tmp_path / MARKER_NAME).exists()
