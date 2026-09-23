"""load_precedent_corpus: flag gating, marker short-circuit, and degrade paths."""
from contextlib import contextmanager
from pathlib import Path

import pytest

from quodeq.context.precedent import (
    MARKER_NAME,
    VectorStoreFns,
    load_precedent_corpus,
    precedent_text,
)
from tests.context.conftest import seed_dismissed


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


def test_loader_excludes_scope_level_and_empty_snippet_dismissals(
    tmp_path: Path, monkeypatch
) -> None:
    """Corpus-side eligibility must mirror match-side ``_semantic_eligible``.

    A scope-level (or empty-snippet/line<=0) dismissal must never enter the
    semantic corpus: its enriched snippet is a whole-file excerpt, so it
    would cosine-match near everything filed under the same requirement.
    The exact-fingerprint tier still covers it (see test_precedent.py); only
    the embedding-backed tier excludes it.
    """
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'", file="auth.py", line=42,
    )
    # Scope-level / empty-snippet dismissal under the SAME requirement: if
    # not excluded corpus-side, its near-blank text would cosine-match
    # almost anything else filed under "S-CON-1".
    seed_dismissed(
        project_dir, "r2",
        req="S-CON-1", snippet="", file="auth.py", line=0, scope="file",
    )

    calls: list[int] = []

    def counting_embed(texts, **kwargs):
        calls.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    corpus = load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=counting_embed, availability_fn=lambda m, b: True,
    )

    assert corpus is not None
    # Exactly one text was ever handed to the embedder: the scope-level /
    # empty-snippet dismissal never made it into the backfill batch.
    assert calls == [1]


def test_loader_uses_injected_vector_store_without_sqlite(tmp_path: Path, monkeypatch) -> None:
    """A fake ``VectorStoreFns`` fully replaces the sqlite-backed store.

    The production resolver is patched to fail on call, so a passing test
    proves the loader touched no sqlite module: every store interaction went
    through the injected callables (in-memory dict), including backfill
    insert, claim release, and the final vector read.
    """
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    monkeypatch.setattr(
        "quodeq.context.precedent_corpus.resolve_vector_store",
        lambda: pytest.fail("production sqlite store resolved despite injected store"),
    )
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'", file="auth.py", line=42,
    )

    conn_sentinel = object()
    stored: dict[str, list[float]] = {}
    released: list[bool] = []

    @contextmanager
    def fake_open(pd, model):
        assert pd == project_dir
        yield conn_sentinel

    def fake_insert(conn, model, items):
        assert conn is conn_sentinel
        stored.update(dict(items))
        return True

    store = VectorStoreFns(
        open_vector_store=fake_open,
        load_vectors=lambda conn: list(stored.items()),
        insert_vectors=fake_insert,
        stored_fingerprints=lambda conn: set(stored),
        try_claim_backfill=lambda conn: True,
        release_backfill_claim=lambda conn: released.append(True),
    )

    corpus = load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=lambda texts, **kw: [[1.0, 0.0] for _ in texts],
        availability_fn=lambda m, b: True,
        store=store,
    )

    assert corpus is not None
    assert corpus.match(precedent_text("S-CON-1", "password = 'secret'")) == pytest.approx(1.0)
    assert len(stored) == 1  # the dismissal was backfilled through the fake
    assert released == [True]  # backfill claim released exactly once


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

    Verifies the loader returns a partial corpus with exactly the first
    dismissed finding's vector, instead of abandoning the whole tier.
    """
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    monkeypatch.setattr("quodeq.context.precedent_store.BACKFILL_CHUNK", 1)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    run_dir = seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'", file="auth.py", line=42,
    )
    seed_dismissed(
        project_dir, "r2",
        req="S-CON-2", snippet="api_key = None", file="db.py", line=7,
    )

    call_count = [0]

    def stateful_embed(texts, **kwargs):
        """Succeeds on the first backfill chunk, raises on the second."""
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
    # Exactly two backfill attempts: chunk 1 (size 1) succeeded, chunk 2
    # failed and stopped the loop -- proves the loop didn't retry forever
    # nor skip straight past the failure.
    assert call_count[0] == 2

    # Prove exactly one vector was stored (not zero, not both): a second
    # load with a fully-working embedder should only need to backfill the
    # one still-missing finding. (No public size accessor exists on
    # PrecedentCorpus, and reaching into the private `_vectors`/`_embed`
    # attributes is exactly what this test used to do and was told not to.)
    second_calls: list[int] = []

    def counting_embed(texts, **kwargs):
        second_calls.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    corpus2 = load_precedent_corpus(
        project_dir, run_dir,
        embed_fn=counting_embed, availability_fn=lambda m, b: True,
    )
    assert corpus2 is not None
    assert second_calls == [1]
