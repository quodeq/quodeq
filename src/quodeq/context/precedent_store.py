"""Vector-store plumbing for the semantic precedent tier.

Owns the six-callable seam (:class:`VectorStoreFns`) that
``load_precedent_corpus`` (see ``precedent_corpus.py``) uses to read/write
the sqlite-backed vector store, plus the backfill loop that embeds
still-missing dismissed findings up to a time/size budget.
"""
from __future__ import annotations

import logging
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.data.sqlite import precedent_vectors as _sqlite_vectors

_logger = logging.getLogger(__name__)

BACKFILL_BUDGET_S = 60.0
BACKFILL_CHUNK = 32

EmbedFn = Callable[..., list[list[float]]]
AvailabilityFn = Callable[[str, str], bool]


@dataclass(frozen=True)
class Embedder:
    """The resolved embedding model, callable, and batch timeout for one corpus build."""

    model: str
    embed_fn: EmbedFn
    batch_timeout: object


@dataclass(frozen=True)
class VectorStoreFns:
    """The six vector-store callables ``load_precedent_corpus`` needs.

    Mirrors the ``embed_fn``/``availability_fn`` seam: tests inject fakes,
    production resolves the sqlite-backed implementations from
    ``data/sqlite/precedent_vectors.py`` via :func:`resolve_vector_store`.
    The connection handle is opaque to this layer -- it is only ever passed
    back into the other five callables.
    """

    open_vector_store: Callable[[Path, str], AbstractContextManager[object | None]]
    load_vectors: Callable[[object], list[tuple[str, list[float]]]]
    insert_vectors: Callable[[object, str, list[tuple[str, list[float]]]], bool]
    stored_fingerprints: Callable[[object], set[str]]
    try_claim_backfill: Callable[[object], bool]
    release_backfill_claim: Callable[[object], None]


def resolve_vector_store() -> VectorStoreFns:
    """Build the production vector-store callables from ``data.sqlite``."""
    return VectorStoreFns(
        open_vector_store=_sqlite_vectors.open_vector_store,
        load_vectors=_sqlite_vectors.load_vectors,
        insert_vectors=_sqlite_vectors.insert_vectors,
        stored_fingerprints=_sqlite_vectors.stored_fingerprints,
        try_claim_backfill=_sqlite_vectors.try_claim_backfill,
        release_backfill_claim=_sqlite_vectors.release_backfill_claim,
    )


def _backfill_missing(
    store: VectorStoreFns,
    conn: object,
    texts: dict[str, str],
    embedder: Embedder,
) -> int:
    """Embed still-missing fingerprints up to the time/size budget.

    Called only while holding the exclusive backfill claim (single writer),
    so it reads the stored set once and computes the missing list once, then
    slices each chunk off that list. Re-querying the table per chunk was an
    N+1 scan, and rescanning ``texts`` per chunk made the loop quadratic in
    the corpus size. Returns how many were newly embedded.
    """
    embedded_new = 0
    deadline = time.monotonic() + BACKFILL_BUDGET_S
    stored = store.stored_fingerprints(conn)
    missing = [fp for fp in texts if fp not in stored]
    chunk_size = BACKFILL_CHUNK
    for start in range(0, len(missing), chunk_size):
        if time.monotonic() >= deadline:
            break
        chunk = missing[start:start + chunk_size]
        try:
            vecs = embedder.embed_fn([texts[fp] for fp in chunk], timeout=embedder.batch_timeout)
        except Exception as exc:  # noqa: BLE001 -- partial corpus is fine
            _logger.warning("Precedent backfill stopped: %s", exc)
            break
        if not store.insert_vectors(conn, embedder.model, list(zip(chunk, vecs))):
            break
        embedded_new += len(chunk)
    return embedded_new


def load_or_backfill_vectors(
    store: VectorStoreFns,
    project_dir: Path,
    texts: dict[str, str],
    embedder: Embedder,
) -> tuple[list[tuple[str, list[float]]], int] | None:
    """Open the vector store, backfill missing fingerprints, return all pairs.

    Returns ``(pairs, embedded_new)`` -- every stored (fingerprint, vector)
    pair and how many were newly embedded in this call -- or None when the
    store couldn't be opened (caller then returns None too). Backfill only
    runs when this process wins the claim (single writer); other readers
    just get whatever is already stored.
    """
    embedded_new = 0
    with store.open_vector_store(project_dir, embedder.model) as conn:
        if conn is None:
            return None
        if store.try_claim_backfill(conn):
            try:
                embedded_new = _backfill_missing(store, conn, texts, embedder)
            finally:
                store.release_backfill_claim(conn)
        pairs = store.load_vectors(conn)
    return pairs, embedded_new
