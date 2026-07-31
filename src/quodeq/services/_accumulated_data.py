"""Data loading helpers for the accumulated (cross-run) view."""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from quodeq.data.fs.report_parser.runs import RunInfo, read_run_data
from quodeq.core.types import DimensionResult

# Files whose contents feed read_run_data for a single run. A completed run is
# not immutable: dismissing a finding or applying a grade formula rewrites the
# SQL grade tables that overlay_sql_grades reads back, so the fingerprint has
# to cover the database (and its write-ahead log, which absorbs writes long
# before a checkpoint touches the main file) alongside the JSON.
_FINGERPRINT_DIRS = ("evaluation", "evidence")
_FINGERPRINT_FILES = ("evaluation.db", "evaluation.db-wal", "events.jsonl")


@dataclass
class _DimensionBuckets:
    """Mutable accumulation buckets used during a single _read_all_run_data pass."""
    latest_by_dimension: dict[str, DimensionResult] = field(default_factory=dict)
    prev_occurrence: dict[str, DimensionResult] = field(default_factory=dict)
    prev_run_latest_map: dict[str, DimensionResult] = field(default_factory=dict)


def _has_valid_score(dim: DimensionResult) -> bool:
    """Return True if the dimension carries a usable, trustworthy score.

    Requires a non-empty ``overall_score`` AND that the model actually
    inspected files. A coverage-0 eval (``files_read == 0``) is the stub
    ``_score_completed_evidence`` writes at cancel time when no findings
    landed; its score is meaningless and must not drive the accumulated
    Overview (the same ``filesRead > 0`` trust rule ``scoring_view`` uses).
    A missing ``files_read`` (None, legacy evals) is trusted as before.
    """
    if not dim.overall_score:
        return False
    return dim.files_read != 0


def _classify_dimension(
    dim: DimensionResult, run_id: str, run_info: RunInfo | None, is_first_run: bool,
    buckets: _DimensionBuckets,
) -> None:
    """Classify a single dimension into latest, previous-occurrence, or previous-run buckets."""
    dim_name = dim.dimension
    if not dim_name:
        return
    if dim_name not in buckets.latest_by_dimension:
        # Only accept as latest if the dimension has a valid score;
        # otherwise keep searching older runs for a scored result.
        if _has_valid_score(dim):
            buckets.latest_by_dimension[dim_name] = replace(
                dim,
                from_run_id=run_id,
                from_date_iso=run_info.date_iso if run_info else None,
                from_date_label=run_info.date_label if run_info else None,
            )
    elif dim_name not in buckets.prev_occurrence:
        buckets.prev_occurrence[dim_name] = replace(dim, run_id=run_id)
    if not is_first_run and dim_name not in buckets.prev_run_latest_map:
        buckets.prev_run_latest_map[dim_name] = dim


def run_fingerprint(run_dir: Path) -> str:
    """Cheap content fingerprint for the inputs ``read_run_data`` reads.

    Stat-based rather than hash-based: the point is to be far cheaper than the
    read it guards, while still changing whenever a run's data is rewritten in
    place (see :data:`_FINGERPRINT_FILES`).
    """
    parts: list[str] = []
    for sub in _FINGERPRINT_DIRS:
        try:
            entries = sorted((run_dir / sub).iterdir())
        except OSError:
            continue
        for path in entries:
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append(f"{sub}/{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    for name in _FINGERPRINT_FILES:
        try:
            stat = (run_dir / name).stat()
        except OSError:
            continue
        parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _strip_findings(dimensions: list[DimensionResult]) -> list[DimensionResult]:
    """Drop the violation/compliance bodies, keeping every scalar field.

    Everything the accumulated walk consults -- ``overall_score``,
    ``files_read``, ``totals``, ``principles`` -- survives, so classification is
    bit-identical to classifying the full read.
    """
    return [replace(d, violations=[], compliance=[]) for d in dimensions]


def make_slim_run_fetcher(
    reports_root: Path, project: str,
    cache: OrderedDict, lock: threading.Lock, max_size: int,
) -> Callable[[str], list[DimensionResult]]:
    """Return a fetcher of findings-free per-run dimensions, LRU-cached.

    The full read costs megabytes per run because it hydrates every finding
    body; the walk over run history needs only the scores. Caching the stripped
    projection instead lets the cache outlive a single request at kilobyte cost,
    which is what makes consecutive as-of selections cheap.

    *max_size* <= 0 disables caching entirely (every call reads through).
    """
    def get_slim(run_id: str) -> list[DimensionResult]:
        if max_size <= 0:
            return _strip_findings(_read_run_data_safely(reports_root, project, run_id))
        key = (str(reports_root), project, run_id,
               run_fingerprint(reports_root / project / run_id))
        with lock:
            hit = cache.get(key)
            if hit is not None:
                cache.move_to_end(key)
                return hit
        slim = _strip_findings(_read_run_data_safely(reports_root, project, run_id))
        with lock:
            cache[key] = slim
            cache.move_to_end(key)
            while len(cache) > max_size:
                cache.popitem(last=False)
        return slim

    return get_slim


def _read_run_data_safely(
    reports_root: Path, project: str, run_id: str,
) -> list[DimensionResult]:
    """``read_run_data`` with the same error tolerance the LRU fetcher applies."""
    try:
        return read_run_data(reports_root, project, run_id)
    except (OSError, ValueError, KeyError):
        return []


def _hydrate_latest_dimensions(
    buckets: _DimensionBuckets, fetch_full: Callable[[str], list[DimensionResult]],
) -> None:
    """Swap the winning slim dimensions for their full findings bodies.

    Only dimensions that survive as *latest* are rendered with violations and
    compliance, and they come from a handful of runs -- so the expensive read is
    paid for those runs alone rather than for the whole history.
    """
    names_by_run: dict[str, list[str]] = {}
    for name, dim in buckets.latest_by_dimension.items():
        if dim.from_run_id:
            names_by_run.setdefault(dim.from_run_id, []).append(name)

    for run_id, names in names_by_run.items():
        full_by_name: dict[str, DimensionResult] = {}
        for dim in fetch_full(run_id):
            # First occurrence wins, matching the classification loop.
            full_by_name.setdefault(dim.dimension, dim)
        for name in names:
            full = full_by_name.get(name)
            if full is None:
                continue
            slim = buckets.latest_by_dimension[name]
            buckets.latest_by_dimension[name] = replace(
                full,
                from_run_id=slim.from_run_id,
                from_date_iso=slim.from_date_iso,
                from_date_label=slim.from_date_label,
            )


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos: list[RunInfo], runs: list[str],
    get_run_data: Callable[[str], list[DimensionResult]] | None = None,
    get_run_slim: Callable[[str], list[DimensionResult]] | None = None,
) -> tuple[dict[str, DimensionResult], dict[str, DimensionResult], list[DimensionResult]]:
    """Build accumulated data structures from a walk over *runs*.

    With *get_run_slim* the walk runs on findings-free dimensions and only the
    winning dimensions are re-read in full; without it the walk reads every run
    in full, as it always did.
    """
    run_lookup = {r.run_id: r for r in all_run_infos}
    buckets = _DimensionBuckets()
    _fetch_full = get_run_data or (lambda rid: read_run_data(reports_root, project, rid))
    _fetch = get_run_slim or _fetch_full

    for run_idx_i, run_id in enumerate(runs):
        run_info = run_lookup.get(run_id)
        for dim in _fetch(run_id):
            _classify_dimension(dim, run_id, run_info, run_idx_i == 0, buckets)

    if get_run_slim is not None:
        _hydrate_latest_dimensions(buckets, _fetch_full)

    return (
        buckets.latest_by_dimension,
        buckets.prev_occurrence,
        list(buckets.prev_run_latest_map.values()),
    )
