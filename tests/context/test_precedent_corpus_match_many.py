"""PrecedentCorpus.match_many: one embed call for a batch of texts (finding
5598). Split from test_precedent_corpus.py to stay under the file-size
ratchet (that file is already over the 240-line sibling-file threshold)."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.context.precedent import MARKER_NAME, PrecedentCorpus


def _corpus(tmp_path: Path, vectors, embed, threshold=0.85) -> PrecedentCorpus:
    return PrecedentCorpus(
        vectors=vectors, embed=embed, threshold=threshold,
        marker_path=tmp_path / MARKER_NAME,
    )


def test_match_many_embeds_the_batch_once(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def embed(texts):
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    corpus = _corpus(tmp_path, vectors=[[1.0, 0.0]], embed=embed)
    scores = corpus.match_many(["a", "b", "c"])

    assert len(calls) == 1 and calls[0] == ["a", "b", "c"]
    assert scores == [pytest.approx(1.0)] * 3


def test_match_many_trips_the_budget_once_for_the_batch(tmp_path: Path, monkeypatch) -> None:
    """A single over-budget match_many call trips the breaker once; a later
    call short-circuits without invoking the embedder again."""
    monkeypatch.setattr("quodeq.context.precedent_corpus._EMBED_BUDGET_S", 0.0)
    calls: list[list[str]] = []

    def embed(texts):
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    corpus = _corpus(tmp_path, vectors=[[1.0, 0.0]], embed=embed)
    scores = corpus.match_many(["a", "b", "c"])

    assert len(calls) == 1
    assert scores == [pytest.approx(1.0)] * 3
    assert (tmp_path / MARKER_NAME).exists()

    # Tripped: the second call returns None for every text without touching
    # the embedder again.
    assert corpus.match_many(["d", "e"]) == [None, None]
    assert len(calls) == 1


def test_match_many_empty_texts_returns_empty_without_embedding(tmp_path: Path) -> None:
    def embed(texts):
        raise AssertionError("embed() called for an empty batch")

    corpus = _corpus(tmp_path, vectors=[[1.0, 0.0]], embed=embed)
    assert corpus.match_many([]) == []


def test_match_many_mismatched_vector_count_trips_and_returns_all_none(tmp_path: Path) -> None:
    """An embed callable that returns the wrong number of vectors must not
    desync `match_many`'s zip of texts to vectors -- it trips the breaker
    and degrades to None for the whole batch instead."""
    calls: list[list[str]] = []

    def embed(texts):
        calls.append(list(texts))
        return [[1.0, 0.0]]  # one vector for three texts

    corpus = _corpus(tmp_path, vectors=[[1.0, 0.0]], embed=embed)
    scores = corpus.match_many(["a", "b", "c"])

    assert scores == [None, None, None]
    assert (tmp_path / MARKER_NAME).exists()

    # Tripped: a later call short-circuits without calling the embedder again.
    assert corpus.match_many(["d"]) == [None]
    assert len(calls) == 1


def test_match_delegates_to_match_many_with_a_single_element_list(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def embed(texts):
        calls.append(list(texts))
        return [[0.9, 0.1]]

    corpus = _corpus(tmp_path, vectors=[[1.0, 0.0], [0.0, 1.0]], embed=embed)
    score = corpus.match("anything")

    assert calls == [["anything"]]
    assert score is not None and score == pytest.approx(0.9939, abs=1e-3)
