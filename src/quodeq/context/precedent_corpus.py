"""Semantic (embedding-backed) precedent matching.

A semantic tier exists behind the ``QUODEQ_SEMANTIC_PRECEDENTS`` flag (off by
default): :class:`PrecedentCorpus` embeds dismissed findings and scores
near-miss matches by cosine similarity, on top of the exact-match fingerprint
tier in ``precedent_fingerprint.py``. Vector-store plumbing (the sqlite-backed
seam and the backfill loop) lives in ``precedent_store.py``.
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Callable

from quodeq.context.precedent_fingerprint import fingerprint, precedent_text
from quodeq.context.precedent_store import (
    AvailabilityFn,
    EmbedFn,
    VectorStoreFns,
    _load_or_backfill_vectors,
)

_logger = logging.getLogger(__name__)

MARKER_NAME = ".semantic_precedents_off"
_EMBED_BUDGET_S = 20.0


def _unit(vec: list[float]) -> list[float] | None:
    norm = math.sqrt(math.sumprod(vec, vec))
    if norm == 0.0:
        return None
    return [x / norm for x in vec]


class PrecedentCorpus:
    """In-memory dismissed-finding vectors plus the embed capability.

    Owns embedding so the analysis enricher never imports llm_bridge (layer
    rules). match() is contractually total: it returns a score or None and
    NEVER raises -- an escaping exception would drop the finding in MCP mode
    (findings_server dispatch catches-and-drops) or crash the API batch.
    """

    def __init__(
        self,
        *,
        vectors: list[list[float]],
        embed: Callable[[list[str]], list[list[float]]],
        threshold: float,
        marker_path: Path,
    ) -> None:
        self._vectors = [u for v in vectors if (u := _unit(v)) is not None]
        self._embed = embed
        self.threshold = threshold
        self._marker_path = marker_path
        self._disabled = False
        self._elapsed = 0.0

    def _trip(self, why: str) -> None:
        self._disabled = True
        _logger.warning("Semantic precedent matching disabled for this run: %s", why)
        try:
            self._marker_path.touch()
        except OSError:
            pass

    def match(self, text: str) -> float | None:
        """Best cosine similarity of *text* against the corpus, or None."""
        if self._disabled or not self._vectors:
            return None
        try:
            start = time.monotonic()
            query = self._embed([text])[0]
            self._elapsed += time.monotonic() - start
            q = _unit(query)
            if q is None:
                return None
            best = max(math.sumprod(q, v) for v in self._vectors)
            if self._elapsed > _EMBED_BUDGET_S:
                self._trip("cumulative embedding time budget exceeded")
            return best
        except Exception as exc:  # noqa: BLE001 -- contractually total
            self._trip(f"embedding failed: {exc}")
            return None


def _collect_dismissed_texts(project_dir: Path) -> dict[str, str]:
    """Map fingerprint -> canonical text for every dismissed finding.

    Mirrors ``_semantic_eligible`` in ``analysis/mcp/enricher.py`` on the
    match side: scope-level and empty-snippet/line<=0 dismissals are
    excluded here too. Without this, a single empty-snippet dismissal
    (``fingerprint`` text like ``"REQ\\n\\n"``) would cosine-match every
    future finding filed under that requirement, and corpus/match-side
    eligibility would be asymmetric.
    """
    from quodeq.data.sqlite.findings_queries import (  # noqa: PLC0415
        read_semantic_eligible_dismissals,
    )

    out: dict[str, str] = {}
    if not project_dir or not project_dir.is_dir():
        return out
    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        for req, snippet in read_semantic_eligible_dismissals(run_dir):
            fp = fingerprint(req, snippet)
            text = precedent_text(req, snippet)
            if fp is not None and text is not None:
                out[fp] = text
    return out


def _resolve_embedding(model: str, base_url: str) -> tuple[EmbedFn, AvailabilityFn, object]:
    """Build the production embed/availability callables from llm_bridge.

    Split out from load_precedent_corpus because assigning a nested
    ``def embed_fn(...)`` over a parameter already annotated
    ``EmbedFn | None`` is a redefinition mypy strict rejects; giving the
    closure its own function with a fresh return-typed binding avoids that.
    Returns ``(embed_fn, availability_fn, batch_timeout)`` -- the timeout is
    the production BATCH_TIMEOUT, used only when the loader explicitly
    overrides the query-time default for backfill chunks.
    """
    from quodeq.llm_bridge._embeddings import (  # noqa: PLC0415
        BATCH_TIMEOUT,
        QUERY_TIMEOUT,
        embed_texts,
        embedding_model_available,
    )

    def _embed(texts: list[str], **kw: object) -> list[list[float]]:
        timeout = kw.get("timeout", QUERY_TIMEOUT)
        return embed_texts(texts, model=model, base_url=base_url, timeout=timeout)  # type: ignore[arg-type]

    return _embed, embedding_model_available, BATCH_TIMEOUT


def _resolve_embed_and_availability(
    embed_fn: EmbedFn | None,
    availability_fn: AvailabilityFn | None,
    model: str,
    base_url: str,
) -> tuple[EmbedFn | None, AvailabilityFn | None, object]:
    """Fill in production embed_fn/availability_fn for whichever is None.

    ``batch_timeout`` is the production BATCH_TIMEOUT when a production
    embed_fn was resolved here, else None (call sites fall back to the
    query-time default).
    """
    batch_timeout: object = None
    if embed_fn is None or availability_fn is None:
        prod_embed_fn, prod_availability_fn, prod_batch_timeout = _resolve_embedding(
            model, base_url
        )
        if embed_fn is None:
            embed_fn = prod_embed_fn
            batch_timeout = prod_batch_timeout
        if availability_fn is None:
            availability_fn = prod_availability_fn
    return embed_fn, availability_fn, batch_timeout


def _resolve_available_embedder(
    embed_fn: EmbedFn | None,
    availability_fn: AvailabilityFn | None,
) -> tuple[str, EmbedFn, object] | None:
    """Resolve model/embed_fn/batch_timeout, or None when unavailable.

    Wraps :func:`_resolve_embed_and_availability` with the model/base_url
    lookup and the availability check + degrade-log, so
    ``load_precedent_corpus`` only has to handle a single
    None-or-proceed branch.
    """
    from quodeq.shared._env import get_embedding_base_url, get_embedding_model  # noqa: PLC0415

    model = get_embedding_model()
    base_url = get_embedding_base_url()
    embed_fn, availability_fn, batch_timeout = _resolve_embed_and_availability(
        embed_fn, availability_fn, model, base_url,
    )
    if not availability_fn(model, base_url):
        _logger.info(
            "Semantic precedent matching off: model %r not found at %s. "
            "Pull it with: ollama pull %s", model, base_url, model,
        )
        return None
    return model, embed_fn, batch_timeout


def _resolve_store() -> VectorStoreFns:
    """Deferred facade lookup so a test's ``monkeypatch.setattr(
    "quodeq.context.precedent._resolve_vector_store", ...)`` takes effect.
    """
    from quodeq.context import precedent as _facade  # noqa: PLC0415 -- deferred facade lookup
    return _facade._resolve_vector_store()


def _embed_and_build_corpus(
    store: VectorStoreFns,
    project_dir: Path,
    model: str,
    texts: dict[str, str],
    embed_fn: EmbedFn,
    batch_timeout: object,
    marker: Path,
    threshold: float,
) -> "PrecedentCorpus | None":
    """Backfill/load vectors and assemble the corpus, or None if nothing embedded."""
    start = time.monotonic()
    result = _load_or_backfill_vectors(
        store, project_dir, model, texts, embed_fn, batch_timeout,
    )
    if result is None:
        return None
    pairs, embedded_new = result

    vectors = [vec for fp, vec in pairs if fp in texts]
    if not vectors:
        _logger.debug("Semantic precedents: nothing embedded yet")
        return None

    corpus = PrecedentCorpus(
        vectors=vectors,
        embed=lambda ts: embed_fn(ts),
        threshold=threshold,
        marker_path=marker,
    )
    _logger.info(
        "Semantic precedent corpus: %d vector(s), %d newly embedded, "
        "model=%s, %dms",
        len(vectors), embedded_new, model,
        int((time.monotonic() - start) * 1000),
    )
    return corpus


def load_precedent_corpus(
    project_dir: Path,
    run_dir: Path,
    *,
    embed_fn: EmbedFn | None = None,
    availability_fn: AvailabilityFn | None = None,
    store: VectorStoreFns | None = None,
) -> "PrecedentCorpus | None":
    """Build the semantic corpus, or None. NEVER raises (never breaks a scan).

    Test seams: *embed_fn*/*availability_fn* default to llm_bridge's
    production callables, *store* to ``data.sqlite.precedent_vectors``. The
    run-dir marker file is the cross-process circuit breaker: one process's
    failure disables the tier for sibling agents, respawns, and per-call API
    context rebuilds.
    """
    from quodeq.shared._env import (  # noqa: PLC0415 -- cross-cutting layer
        get_precedent_similarity_threshold,
        semantic_precedents_enabled,
    )

    if not semantic_precedents_enabled():
        _logger.debug("Semantic precedents: flag off")
        return None
    marker = run_dir / MARKER_NAME
    try:
        if marker.exists():
            _logger.debug("Semantic precedents: circuit marker present")
            return None

        resolved = _resolve_available_embedder(embed_fn, availability_fn)
        if resolved is None:
            return None
        model, embed_fn, batch_timeout = resolved

        texts = _collect_dismissed_texts(project_dir)
        if not texts:
            _logger.debug("Semantic precedents: no dismissed findings")
            return None
        if store is None:
            store = _resolve_store()

        return _embed_and_build_corpus(
            store, project_dir, model, texts, embed_fn, batch_timeout,
            marker, get_precedent_similarity_threshold(),
        )
    except Exception as exc:  # noqa: BLE001 -- never break a scan
        _logger.warning("Semantic precedent corpus unavailable: %s", exc)
        return None
