"""PrecedentCorpus: matching, budgets, circuit breaker, loader degrade paths."""
import math
from pathlib import Path

import pytest

from quodeq.context.precedent import (
    MARKER_NAME,
    PrecedentCorpus,
    load_precedent_corpus,
    precedent_text,
)
from tests.context.conftest import seed_dismissed


def _unit(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec]


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


def test_loader_flag_off_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QUODEQ_SEMANTIC_PRECEDENTS", raising=False)
    assert load_precedent_corpus(tmp_path, tmp_path) is None


def test_loader_marker_short_circuits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / MARKER_NAME).touch()
    assert load_precedent_corpus(tmp_path, run_dir) is None


def test_loader_end_to_end_with_fake_embedder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'", file="auth.py", line=42,
    )

    def fake_embed(texts, **kwargs):
        return [[1.0, 0.0] for _ in texts]

    corpus = load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=fake_embed, availability_fn=lambda m, b: True,
    )
    assert corpus is not None
    assert corpus.match(precedent_text("S-CON-1", "password = 'secret'")) == pytest.approx(1.0)
    # Second load reads vectors from the store without re-embedding.
    calls: list[int] = []

    def counting_embed(texts, **kwargs):
        calls.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    corpus2 = load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=counting_embed, availability_fn=lambda m, b: True,
    )
    assert corpus2 is not None
    assert calls == []  # backfill had nothing to do


def test_loader_model_unavailable_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    project_dir = tmp_path / "p"
    project_dir.mkdir()
    run_dir = project_dir / "r"
    run_dir.mkdir()
    assert load_precedent_corpus(
        project_dir, run_dir, availability_fn=lambda m, b: False,
    ) is None


def test_loader_embed_failure_with_nothing_stored_degrades_to_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'", file="auth.py", line=42,
    )

    def broken_embed(texts, **kwargs):
        raise RuntimeError("server 500")

    # Backfill fails -> nothing stored yet -> corpus is None, but NO exception.
    assert load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=broken_embed, availability_fn=lambda m, b: True,
    ) is None


def test_loader_embed_failure_partial_corpus(tmp_path: Path, monkeypatch) -> None:
    """Seed two findings, embed first chunk successfully, fail on second chunk.

    Verifies the loader returns a partial corpus with at least the first
    dismissed finding's vector, instead of abandoning the whole tier.
    """
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    monkeypatch.setattr("quodeq.context.precedent._BACKFILL_CHUNK", 1)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'", file="auth.py", line=42,
    )
    seed_dismissed(
        project_dir, run_dir,
        req="S-CON-2", snippet="api_key = None", file="db.py", line=7,
    )

    call_count = [0]

    def stateful_embed(texts, **kwargs):
        """Succeeds on first call, raises on subsequent calls."""
        call_count[0] += 1
        if call_count[0] > 1:
            raise RuntimeError("server 500")
        # Return vectors for the requested texts.
        return [[1.0, 0.0] for _ in texts]

    corpus = load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=stateful_embed, availability_fn=lambda m, b: True,
    )

    # Corpus is not None: partial is better than nothing.
    assert corpus is not None
    # Patch the corpus's embed to succeed for matching (backfill failed partway).
    corpus._embed = lambda texts: [[1.0, 0.0] for _ in texts]
    # We can match against the first finding (which was embedded before failure).
    score = corpus.match(precedent_text("S-CON-1", "password = 'secret'"))
    assert score is not None and score == pytest.approx(1.0)
