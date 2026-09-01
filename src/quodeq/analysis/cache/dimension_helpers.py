"""Dimension-level cache helpers — bridge between RunConfig + filesystem
and the cache layer.

These are pure functions used by the V2 dimension processor (Phase B5):

  - ``build_cache_key_for_file``: derive a deterministic cache key from
    the current ``RunConfig`` and a target file. The key composition
    matches ``CacheKey``: file content, dimension, standards, prompts,
    model, language. Sampling params are not yet plumbed through
    ``AnalysisOptions``; once they are, add them to the key.

  - ``classify_files_via_cache``: split a file list into cache hits
    (with findings) and misses (need dispatch). The miss-key mapping is
    returned so the caller can write entries after dispatch without
    recomputing keys.

  - ``persist_dispatch_results``: after a dispatch run writes its JSONL,
    group its findings by file and write per-file cache entries for the
    files that were actually dispatched. Empty-finding files get an
    empty entry — a clean analysis is still a hit, not a miss.

These helpers compose into the canonical V2 dimension processor in
``cache/dimension_runner.py``.

Cache-key composition and provenance-drift tracking live in
``_key_provenance.py`` and are re-exported below for backward compatibility.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache._key_provenance import (
    _SCHEMA_VERSION,
    _accumulate_drift,
    _current_provenance,
    _hash_prompts_combined,
    _model_id_from,
    build_cache_key_for_file,
    format_provenance_drift,  # noqa: F401 -- re-export
)
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry, build_provenance, quodeq_version
from quodeq.analysis.fingerprint import (
    _hash_file,
    _hash_standards,
    dimension_params_state,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifyResult:
    """Result of splitting a file list against the cache."""

    cached_findings: list[dict] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    # Per-file cache key for the missed files, so the caller can write
    # entries after dispatch without recomputing the key.
    miss_keys: dict[str, str] = field(default_factory=dict)
    # Per-field drift among cache hits: field -> {"count", "from", "to"}.
    # Only fields that actually drifted appear. Lets the caller surface how
    # many reused findings predate the current model / standards / prompts,
    # so reuse across those boundaries is never silent.
    provenance_drift: dict = field(default_factory=dict)
    # Hits from entries no COMPLETED run has consolidated yet: the producing
    # run was cancelled with "keep findings", failed, or was killed, so the
    # user was never shown these findings in an Overview. Kept apart from
    # cached_findings so the replay path leaves them unstamped and the live
    # feed shows them as this scan's own.
    unconsolidated_findings: list[dict] = field(default_factory=list)
    # file -> cache key for those same entries, so a run that reaches done
    # can flip them to consolidated.
    unconsolidated_hit_keys: dict[str, str] = field(default_factory=dict)


def _classify_one_file(
    config: RunConfig, dimension: str, f: str, cache: CacheBackend, *, bypass_reads: bool,
    current_prov: dict | None,
) -> tuple[str, CacheEntry | None, dict | None]:
    """Classify one file against the cache. Returns (key, hit, current_prov),
    where hit is None on a miss and current_prov is lazily computed on the
    first hit (passed through so the caller only pays for it once)."""
    key = build_cache_key_for_file(config, f, dimension)
    hit = None if bypass_reads else cache.get(key)
    if hit is not None and current_prov is None:
        current_prov = _current_provenance(config, dimension)
    return key, hit, current_prov


def classify_files_via_cache(
    config: RunConfig, dimension: str, files: list[str],
    cache: CacheBackend,
    *, bypass_reads: bool = False,
) -> ClassifyResult:
    """Split ``files`` into cache hits (findings) and misses (need dispatch).

    When ``bypass_reads`` is True (e.g. honoring ``--clean-scan``), every
    file is forced into the misses bucket regardless of cache state. The
    miss_keys map is still populated so callers can write fresh entries
    after dispatch — clean-scan refreshes the cache rather than ignoring it.

    The pipeline classifies twice per dim (estimates + dim runner). When
    ``config._classify_cache`` is set to a dict, this function stashes
    its result there on the first call for a given ``(dimension, files)``
    pair and short-circuits the second call. The stash MUST NOT short-
    circuit when ``bypass_reads`` is True — clean-scan deletes entries
    immediately before this call, so an upfront classify's hits are
    stale by the time the dim runner asks again.
    """
    files_tuple = tuple(files)
    run_cache = config._classify_cache
    if not bypass_reads and run_cache is not None:
        stashed = run_cache.get(dimension)
        if stashed is not None and stashed[0] == files_tuple:
            return stashed[1]

    cached_findings: list[dict] = []
    misses: list[str] = []
    miss_keys: dict[str, str] = {}
    provenance_drift: dict = {}
    unconsolidated_findings: list[dict] = []
    unconsolidated_hit_keys: dict[str, str] = {}
    current_prov: dict | None = None  # computed lazily, only if there are hits
    for f in files:
        key, hit, current_prov = _classify_one_file(
            config, dimension, f, cache, bypass_reads=bypass_reads, current_prov=current_prov,
        )
        if hit is None:
            misses.append(f)
            miss_keys[f] = key
        else:
            if hit.consolidated:
                cached_findings.extend(hit.findings)
            else:
                unconsolidated_findings.extend(hit.findings)
                unconsolidated_hit_keys[f] = key
            assert current_prov is not None  # set on the first hit, above
            _accumulate_drift(provenance_drift, hit.provenance or {}, current_prov)
    result = ClassifyResult(
        cached_findings=cached_findings,
        misses=misses,
        miss_keys=miss_keys,
        provenance_drift=provenance_drift,
        unconsolidated_findings=unconsolidated_findings,
        unconsolidated_hit_keys=unconsolidated_hit_keys,
    )
    if not bypass_reads and run_cache is not None:
        run_cache[dimension] = (files_tuple, result)
    return result


def _group_findings_by_file(jsonl_path: Path) -> tuple[dict[str, list[dict]], set[str]]:
    """Read a JSONL of findings + markers and return (grouped_findings, ok_files).

    Marker lines are recognised by the ``_marker`` key and excluded from the
    grouped findings. ``ok_files`` contains the set of files whose *most
    recent* file_done marker has status='ok'. Files whose latest marker is
    'error' (or have no marker at all) are not in the set.
    """
    grouped: dict[str, list[dict]] = {}
    last_status: dict[str, str] = {}
    if not jsonl_path.is_file():
        return grouped, set()
    try:
        text = jsonl_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.warning("failed to read JSONL %s: %s", jsonl_path, exc)
        return grouped, set()
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if entry.get("_marker") == "file_done":
            f = entry.get("file")
            status = entry.get("status")
            if isinstance(f, str) and status in ("ok", "error"):
                last_status[f] = status
            continue
        f = entry.get("file")
        if isinstance(f, str) and f:
            grouped.setdefault(f, []).append(entry)
    ok_files = {f for f, s in last_status.items() if s == "ok"}
    return grouped, ok_files


def _build_cache_entry_for_file(
    config: RunConfig, dimension: str, f: str, key: str, grouped: dict[str, list[dict]],
    *, model_id: str, standards_hash: str, prompts_hash: str, effective_params: dict,
    version: str,
) -> CacheEntry:
    """Build the CacheEntry for one dispatched file's persisted result."""
    return CacheEntry(
        key=key,
        schema_version=_SCHEMA_VERSION,
        findings=grouped.get(f, []),
        files_read=1,
        file_path=f,
        dimension=dimension,
        model_id=model_id,
        file_content_hash=_hash_file(config.src / f) or "",
        language=config.language or "",
        provenance=build_provenance(
            model_id=model_id, prompts_hash=prompts_hash,
            standards_hash=standards_hash, version=version,
            effective_params=effective_params,
        ),
        # Born unconsolidated: no completed run has these findings in its
        # report yet. mark_run_consolidated flips it when this run ends done.
        #
        # Accepted race: two concurrent runs on one project can both treat
        # file X as a miss. If run A reaches done and flips X to
        # consolidated, run B's periodic-persist watcher can then rewrite
        # X here with consolidated=False. If B is later cancelled, X reads
        # as unconsolidated even though A already put those findings in a
        # completed Overview, so the next run surfaces them as "new" once.
        # Cosmetic, requires concurrent runs on one project, and
        # self-heals on the next done run. Not fixing.
        consolidated=False,
    )


def persist_dispatch_results(
    config: RunConfig, dimension: str, *, miss_files: list[str],
    jsonl_path: Path, miss_keys: dict[str, str], cache: CacheBackend,
) -> None:
    """Write per-file cache entries for files with a file_done='ok' marker.

    Files in *miss_files* that lack an ok marker (worker crashed, token-out,
    abandoned) are NOT cached, so the next run re-dispatches them.
    """
    if not jsonl_path.is_file():
        return
    grouped, ok_files = _group_findings_by_file(jsonl_path)
    model_id = _model_id_from(config)
    # Provenance context — run-constant, computed once. These left the cache
    # key in schema 3; recording them keeps each entry self-describing.
    standards_hash = (
        _hash_standards(config.standards_dir, dimension, config.src)
        if config.standards_dir else ""
    ) or ""
    _, effective_params = dimension_params_state(
        config.standards_dir, dimension, config.src,
    )
    prompts_hash = _hash_prompts_combined(config.prompts_dir)
    version = quodeq_version()
    for f in miss_files:
        if f not in ok_files:
            continue
        key = miss_keys.get(f)
        if key is None:
            _logger.debug("persist_dispatch_results: no key for %s; skipping", f)
            continue
        entry = _build_cache_entry_for_file(
            config, dimension, f, key, grouped,
            model_id=model_id, standards_hash=standards_hash, prompts_hash=prompts_hash,
            effective_params=effective_params, version=version,
        )
        cache.put(key, entry)
