"""Project-local precedent matching for the context-enricher pipeline -- facade.

A precedent is a finding that was previously dismissed for this project.
On the next evaluation, the scanner will likely surface the same code
pattern again; without precedent tracking, the user has to dismiss it
every run.

This module is the stable import path every caller (and every patch target)
uses; the implementation is split across three siblings:

- ``precedent_fingerprint.py`` -- exact-match fingerprinting
  (``fingerprint``, ``_normalize_snippet``, ``precedent_text``,
  ``load_precedent_fingerprints``).
- ``precedent_store.py`` -- the sqlite-backed vector-store seam and its
  backfill loop (``VectorStoreFns``, ``_resolve_vector_store``,
  ``_load_or_backfill_vectors``).
- ``precedent_corpus.py`` -- the semantic matcher and its loader
  (``PrecedentCorpus``, ``load_precedent_corpus``, and their helpers).

``precedent_corpus.py`` and ``precedent_store.py`` look up
``_resolve_vector_store`` and ``_BACKFILL_CHUNK`` back through this module
(a deferred facade lookup, not a bare name) so that
``monkeypatch.setattr("quodeq.context.precedent.<name>", ...)`` in tests
still reaches the real call sites.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-exports -- exact-match fingerprinting
# ---------------------------------------------------------------------------
from quodeq.context.precedent_fingerprint import (  # noqa: F401 — re-export
    _normalize_snippet,
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
    _BACKFILL_BUDGET_S,
    _BACKFILL_CHUNK,
    _load_or_backfill_vectors,
    _resolve_vector_store,
)

# ---------------------------------------------------------------------------
# Re-exports -- semantic corpus and loader
# ---------------------------------------------------------------------------
from quodeq.context.precedent_corpus import (  # noqa: F401 — re-export
    MARKER_NAME,
    PrecedentCorpus,
    _EMBED_BUDGET_S,
    _collect_dismissed_texts,
    _resolve_embed_and_availability,
    _resolve_embedding,
    _unit,
    load_precedent_corpus,
)
