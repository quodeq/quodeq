"""Project-local precedent matching for the context-enricher pipeline.

A precedent is a finding that was previously dismissed for this project.
On the next evaluation, the scanner will likely surface the same code
pattern again; without precedent tracking, the user has to dismiss it
every run. This module computes a stable fingerprint for each dismissed
finding so the post-LLM pipeline can downweight matches.

Fingerprint = sha256 of ``(req, normalized_snippet)``. Whitespace and
trailing punctuation are normalized so cosmetic edits to surrounding
code don't break the match. Code identifiers are *not* normalized:
renaming a variable produces legitimately different code.

A semantic tier now exists behind the ``QUODEQ_SEMANTIC_PRECEDENTS`` flag
(off by default): :class:`PrecedentCorpus` embeds dismissed findings and
scores near-miss matches by cosine similarity, on top of the exact-match
fingerprint above.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.data.ports.precedents import DismissedSnippetsReader

_logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")


def _normalize_snippet(snippet: str | None) -> str:
    """Collapse runs of whitespace and trim trailing punctuation/space."""
    if not snippet:
        return ""
    collapsed = _WS_RE.sub(" ", snippet).strip()
    return collapsed.rstrip(",;.")


def fingerprint(req: str | None, snippet: str | None) -> str | None:
    """Hex sha256 of ``req + '|' + normalized_snippet``, or None when blank.

    Returning None for blank inputs lets callers skip lookup entirely
    instead of poisoning the precedent set with a useless all-empty key.
    """
    norm = _normalize_snippet(snippet)
    req_part = (req or "").strip()
    if not req_part and not norm:
        return None
    payload = f"{req_part}|{norm}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_precedent_fingerprints(
    project_dir: Path, *, read_dismissed: DismissedSnippetsReader | None = None,
) -> set[str]:
    """Load fingerprints for every dismissed finding in *project_dir*.

    Aggregates across ``<run_id>/evaluation.db`` under *project_dir*. Missing
    or locked DBs are skipped -- precedent matching degrades gracefully and
    never breaks a scan.

    *read_dismissed* is a test seam (see ``data/ports/precedents.py``);
    production callers should inject
    ``quodeq.data.sqlite.findings_queries.read_dismissed_snippets``
    explicitly. Left unset, it's resolved lazily below -- the local import
    avoids a cycle (``data.fs.repo_clone`` -> ``context`` -> here ->
    ``data.sqlite`` would close a loop if this were a top-level import).

    Legacy note: prior to PR 1 (live-grades), dismissals were stored in
    ``<project_dir>/dismissed.json``. The migration in
    ``data/migrations/dismissed_json_to_actions_log.py`` folds those legacy
    entries into ``actions.jsonl`` on first projection, so once a project has
    been opened post-deploy the SQL rows also capture the historical data.
    """
    if not project_dir or not project_dir.is_dir():
        return set()

    if read_dismissed is None:
        from quodeq.data.sqlite.findings_queries import read_dismissed_snippets  # noqa: PLC0415
        read_dismissed = read_dismissed_snippets

    out: set[str] = set()
    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        for req, snippet in read_dismissed(run_dir):
            fp = fingerprint(req, snippet)
            if fp is not None:
                out.add(fp)
    return out


MARKER_NAME = ".semantic_precedents_off"
_EMBED_BUDGET_S = 20.0
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


def precedent_text(req: str | None, snippet: str | None) -> str | None:
    """Canonical text embedded for a finding -- used on BOTH store and match
    sides so the comparison is symmetric. None when both parts are blank.

    Note: ``.rstrip()`` on top of ``_normalize_snippet`` mops up the trailing
    space that punctuation-stripping can leave behind (e.g. "x = 1 ;" ->
    "x = 1 "); it's applied here rather than in ``_normalize_snippet``
    itself so ``fingerprint()``'s hash stays byte-for-byte unchanged.
    """
    norm = _normalize_snippet(snippet).rstrip()
    req_part = (req or "").strip()
    if not req_part and not norm:
        return None
    return f"{req_part}\n\n{norm}"


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


def load_precedent_corpus(
    project_dir: Path,
    run_dir: Path,
    *,
    embed_fn: EmbedFn | None = None,
    availability_fn: AvailabilityFn | None = None,
    store: VectorStoreFns | None = None,
) -> "PrecedentCorpus | None":
    """Build the semantic corpus, or None. NEVER raises (never breaks a scan).

    *embed_fn* / *availability_fn* / *store* are test seams; production
    resolves the first two from llm_bridge and *store* from
    ``data.sqlite.precedent_vectors``. The run-dir marker file is the
    cross-process circuit breaker: one process's failure disables the tier
    for sibling agents, respawns, and per-call API context rebuilds.
    """
    from quodeq.shared._env import (  # noqa: PLC0415 -- cross-cutting layer
        get_embedding_base_url,
        get_embedding_model,
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

        model = get_embedding_model()
        base_url = get_embedding_base_url()
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

        if not availability_fn(model, base_url):
            _logger.info(
                "Semantic precedent matching off: model %r not found at %s. "
                "Pull it with: ollama pull %s", model, base_url, model,
            )
            return None

        texts = _collect_dismissed_texts(project_dir)
        if not texts:
            _logger.debug("Semantic precedents: no dismissed findings")
            return None

        if store is None:
            store = _resolve_vector_store()

        start = time.monotonic()
        embedded_new = 0
        with store.open_vector_store(project_dir, model) as conn:
            if conn is None:
                return None
            if store.try_claim_backfill(conn):
                try:
                    deadline = time.monotonic() + _BACKFILL_BUDGET_S
                    # We hold the exclusive backfill claim, so no other writer
                    # adds fingerprints while we run. Read the stored set once and
                    # track inserts locally instead of re-querying the whole
                    # (growing) table on every chunk -- that was an N+1 scan whose
                    # cost climbed with the corpus size.
                    stored = store.stored_fingerprints(conn)
                    while time.monotonic() < deadline:
                        missing = [fp for fp in texts if fp not in stored]
                        if not missing:
                            break
                        chunk = missing[:_BACKFILL_CHUNK]
                        try:
                            vecs = embed_fn(
                                [texts[fp] for fp in chunk], timeout=batch_timeout,
                            )
                        except Exception as exc:  # noqa: BLE001 -- partial corpus is fine
                            _logger.warning("Precedent backfill stopped: %s", exc)
                            break
                        if not store.insert_vectors(conn, model, list(zip(chunk, vecs))):
                            break
                        stored.update(chunk)
                        embedded_new += len(chunk)
                finally:
                    store.release_backfill_claim(conn)
            pairs = store.load_vectors(conn)

        vectors = [vec for fp, vec in pairs if fp in texts]
        if not vectors:
            _logger.debug("Semantic precedents: nothing embedded yet")
            return None

        corpus = PrecedentCorpus(
            vectors=vectors,
            embed=lambda ts: embed_fn(ts),
            threshold=get_precedent_similarity_threshold(),
            marker_path=marker,
        )
        _logger.info(
            "Semantic precedent corpus: %d vector(s), %d newly embedded, "
            "model=%s, %dms",
            len(vectors), embedded_new, model,
            int((time.monotonic() - start) * 1000),
        )
        return corpus
    except Exception as exc:  # noqa: BLE001 -- never break a scan
        _logger.warning("Semantic precedent corpus unavailable: %s", exc)
        return None
