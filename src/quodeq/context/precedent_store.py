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

_logger = logging.getLogger(__name__)

_BACKFILL_BUDGET_S = 60.0
_BACKFILL_CHUNK = 32

EmbedFn = Callable[..., list[list[float]]]
AvailabilityFn = Callable[[str, str], bool]


@dataclass(frozen=True)
class VectorStoreFns:
    """The six vector-store callables ``load_precedent_corpus`` needs.

    Mirrors the ``embed_fn``/``availability_fn`` seam: tests inject fakes,
    production resolves the sqlite-backed implementations from
    ``data/sqlite/precedent_vectors.py`` via :func:`_resolve_vector_store`.
    The connection handle is opaque to this layer -- it is only ever passed
    back into the other five callables.
    """

    open_vector_store: Callable[[Path, str], AbstractContextManager[object | None]]
    load_vectors: Callable[[object], list[tuple[str, list[float]]]]
    insert_vectors: Callable[[object, str, list[tuple[str, list[float]]]], bool]
    stored_fingerprints: Callable[[object], set[str]]
    try_claim_backfill: Callable[[object], bool]
    release_backfill_claim: Callable[[object], None]


def _resolve_vector_store() -> VectorStoreFns:
    """Build the production vector-store callables from ``data.sqlite``.

    Local import for the same reason as ``load_precedent_fingerprints``'s
    lazy default: a top-level ``data.sqlite`` import would close the
    ``data.fs.repo_clone`` -> ``context`` -> ``data.sqlite`` loop.
    """
    from quodeq.data.sqlite.precedent_vectors import (  # noqa: PLC0415
        insert_vectors,
        load_vectors,
        open_vector_store,
        release_backfill_claim,
        stored_fingerprints,
        try_claim_backfill,
    )

    return VectorStoreFns(
        open_vector_store=open_vector_store,
        load_vectors=load_vectors,
        insert_vectors=insert_vectors,
        stored_fingerprints=stored_fingerprints,
        try_claim_backfill=try_claim_backfill,
        release_backfill_claim=release_backfill_claim,
    )


def _backfill_missing(
    store: VectorStoreFns,
    conn: object,
    model: str,
    texts: dict[str, str],
    embed_fn: EmbedFn,
    batch_timeout: object,
) -> int:
    """Embed still-missing fingerprints up to the time/size budget.

    Called only while holding the exclusive backfill claim (single writer),
    so it reads the stored set once and tracks inserts locally instead of
    re-querying the whole (growing) table on every chunk -- that was an N+1
    scan whose cost climbed with the corpus size. Returns how many were
    newly embedded.

    ``_BACKFILL_CHUNK`` is read off the facade module (``context.precedent``)
    rather than this module's own global, so a test's
    ``monkeypatch.setattr("quodeq.context.precedent._BACKFILL_CHUNK", ...)``
    still takes effect here.
    """
    from quodeq.context import precedent as _facade  # noqa: PLC0415 -- deferred facade lookup

    embedded_new = 0
    deadline = time.monotonic() + _BACKFILL_BUDGET_S
    stored = store.stored_fingerprints(conn)
    while time.monotonic() < deadline:
        missing = [fp for fp in texts if fp not in stored]
        if not missing:
            break
        chunk = missing[:_facade._BACKFILL_CHUNK]
        try:
            vecs = embed_fn([texts[fp] for fp in chunk], timeout=batch_timeout)
        except Exception as exc:  # noqa: BLE001 -- partial corpus is fine
            _logger.warning("Precedent backfill stopped: %s", exc)
            break
        if not store.insert_vectors(conn, model, list(zip(chunk, vecs))):
            break
        stored.update(chunk)
        embedded_new += len(chunk)
    return embedded_new


def _load_or_backfill_vectors(
    store: VectorStoreFns,
    project_dir: Path,
    model: str,
    texts: dict[str, str],
    embed_fn: EmbedFn,
    batch_timeout: object,
) -> tuple[list[tuple[str, list[float]]], int] | None:
    """Open the vector store, backfill missing fingerprints, return all pairs.

    Returns ``(pairs, embedded_new)`` -- every stored (fingerprint, vector)
    pair and how many were newly embedded in this call -- or None when the
    store couldn't be opened (caller then returns None too). Backfill only
    runs when this process wins the claim (single writer); other readers
    just get whatever is already stored.
    """
    embedded_new = 0
    with store.open_vector_store(project_dir, model) as conn:
        if conn is None:
            return None
        if store.try_claim_backfill(conn):
            try:
                embedded_new = _backfill_missing(
                    store, conn, model, texts, embed_fn, batch_timeout,
                )
            finally:
                store.release_backfill_claim(conn)
        pairs = store.load_vectors(conn)
    return pairs, embedded_new
