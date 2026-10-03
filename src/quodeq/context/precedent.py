"""Project-local precedent matching for the context-enricher pipeline -- facade.

A precedent is a finding that was previously dismissed for this project.
On the next evaluation, the scanner will likely surface the same code
pattern again; without precedent tracking, the user has to dismiss it
every run.

This module is the stable import path every caller (and every patch target)
uses; the implementation is split across three siblings:

- ``precedent_fingerprint.py`` -- exact-match fingerprinting
  (``fingerprint``, ``precedent_text``, ``load_precedent_fingerprints``).
- ``precedent_store.py`` -- the sqlite-backed vector-store seam and its
  backfill loop (``VectorStoreFns``, ``resolve_vector_store``,
  ``load_or_backfill_vectors``).
- ``precedent_corpus.py`` -- the semantic matcher and its loader
  (``PrecedentCorpus``, ``load_precedent_corpus``, and their helpers).

Patch ``resolve_vector_store`` on ``precedent_corpus`` and ``BACKFILL_CHUNK``
on ``precedent_store``: the siblings read their own module globals, and this
facade never gets imported back by them.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-exports -- exact-match fingerprinting
# ---------------------------------------------------------------------------
from quodeq.context.precedent_fingerprint import (  # noqa: F401 — re-export
    fingerprint,
    load_precedent_fingerprints,
    precedent_text,
)

# ---------------------------------------------------------------------------
# Re-exports -- vector-store plumbing
# ---------------------------------------------------------------------------
from quodeq.context.precedent_store import (  # noqa: F401 — re-export
    AvailabilityFn,
    EmbedFn,
    VectorStoreFns,
    BACKFILL_BUDGET_S,
    BACKFILL_CHUNK,
    load_or_backfill_vectors,
    resolve_vector_store,
)

# ---------------------------------------------------------------------------
# Re-exports -- semantic corpus and loader
# ---------------------------------------------------------------------------
from quodeq.context.precedent_corpus import (  # noqa: F401 — re-export
    MARKER_NAME,
    PrecedentCorpus,
    EMBED_BUDGET_S,
    collect_dismissed_texts,
    resolve_embed_and_availability,
    resolve_embedding,
    unit,
    load_precedent_corpus,
)
