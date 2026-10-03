"""Data loading helpers for the accumulated (cross-run) view."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from quodeq.services.wiring import RunInfo, read_run_data, read_run_manifest, read_run_scalars, run_fingerprint
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import DimensionResult
from quodeq.core.types.dimension import open_types_of
from quodeq.shared.constants import JSON_SUFFIX

# A run's per-dimension evaluation reports; without them the full read yields no
# dimensions, so the scalar read (which would still find grade rows) must not be used.
_EVALUATION_DIR = "evaluation"


@dataclass
class _DimensionBuckets:
    """Mutable accumulation buckets used during a single read_all_run_data pass."""
    latest_by_dimension: dict[str, DimensionResult] = field(default_factory=dict)
    prev_occurrence: dict[str, DimensionResult] = field(default_factory=dict)
    prev_run_latest_map: dict[str, DimensionResult] = field(default_factory=dict)


def has_valid_score(dim: DimensionResult) -> bool:
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
        if has_valid_score(dim):
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


def slim_dimensions(dimensions: list[DimensionResult]) -> list[DimensionResult]:
    """Drop the violation/compliance bodies, keeping every scalar field.

    Everything the accumulated walk consults -- ``overall_score``,
    ``files_read``, ``totals``, ``principles`` -- survives, so classification is
    bit-identical to classifying the full read. The count of open requirement
    types is taken before the findings go, because the Overview hero reads it
    and a slim dimension has no findings left to count.
    """
    return [replace(d, violations=[], compliance=[], open_types=open_types_of(d)) for d in dimensions]


def make_slim_run_fetcher(
    reports_root: Path, project: str,
    cache: OrderedDict, lock: threading.Lock, max_size: int,
    *, log: LogSink = NULL_LOG,
) -> Callable[[str], list[DimensionResult]]:
    """Return a fetcher of findings-free per-run dimensions, LRU-cached.

    The full read costs megabytes per run because it hydrates every finding
    body; the walk over run history needs only the scores. Caching the stripped
    projection instead lets the cache outlive a single request at kilobyte cost,
    which is what makes consecutive as-of selections cheap.

    *max_size* <= 0 disables caching entirely (every call reads through).
    """
    def read_slim(run_id: str) -> list[DimensionResult]:
        return slim_dimensions(read_scalar_dimensions(reports_root, project, run_id, log=log))

    def get_slim(run_id: str) -> list[DimensionResult]:
        if max_size <= 0:
            return read_slim(run_id)
        key = (str(reports_root), project, run_id,
               run_fingerprint(reports_root / project / run_id))
        with lock:
            hit = cache.get(key)
            if hit is not None:
                cache.move_to_end(key)
                return hit
        slim = read_slim(run_id)
        with lock:
            cache[key] = slim
            cache.move_to_end(key)
            while len(cache) > max_size:
                cache.popitem(last=False)
        return slim

    return get_slim


def _report_dimensions(run_dir: Path) -> set[str]:
    """Dimensions with an evaluation report (``evaluation/<dimension>.json``) in *run_dir*."""
    eval_dir = run_dir / _EVALUATION_DIR
    if not eval_dir.is_dir():
        return set()
    return {p.stem for p in eval_dir.iterdir() if p.suffix == JSON_SUFFIX}


def _scalars_match_reports(dims: list[DimensionResult], reports: set[str]) -> bool:
    """True when the scalar read answers what a full read would for winner selection.

    The dimension set must equal the reports on disk, and no dimension may carry
    ``files_read == 0``: the grade table stores an unrecorded count as 0, which a
    full read reports as unknown (trusted) and the scalar row as a coverage-0 stub.
    """
    return {d.dimension for d in dims} == reports and all(d.files_read != 0 for d in dims)


def read_scalar_dimensions(
    reports_root: Path, project: str, run_id: str,
    *, log: LogSink = NULL_LOG,
    full_reader: Callable[[Path, str, str], list[DimensionResult]] | None = None,
    scalar_reader: Callable[..., list[DimensionResult]] = read_run_scalars,
) -> list[DimensionResult]:
    """One run's per-dimension scores, grades, counts and files read, without its findings.

    Served from the run database's grade tables (*scalar_reader*, default
    ``read_run_scalars``), a few aggregate rows instead of every finding,
    whenever that answers exactly what the full read would
    (``_scalars_match_reports``); otherwise *full_reader* (default: the
    tolerant full read). Winning dimensions that need their findings are
    re-read in full by the caller.
    """
    def _full(root: Path, proj: str, rid: str) -> list[DimensionResult]:
        if full_reader is not None:
            return full_reader(root, proj, rid)
        return _read_run_data_safely(root, proj, rid, log=log)

    reports = _report_dimensions(reports_root / project / run_id)
    if not reports:
        return _full(reports_root, project, run_id)
    try:
        dims = scalar_reader(reports_root, project, run_id, fallback_reader=_full)
    except (OSError, ValueError, KeyError) as exc:
        log.warning(f"read_run_scalars failed for {run_id}: {exc}")
        return []
    return dims if _scalars_match_reports(dims, reports) else _full(reports_root, project, run_id)


def run_source_file_count(run_dir: Path) -> int | None:
    """The run's source file count from its evidence manifest, the value a full read carries."""
    count = (read_run_manifest(run_dir) or {}).get("source_files_count")
    return count if isinstance(count, int) and count > 0 else None


def _read_run_data_safely(
    reports_root: Path, project: str, run_id: str, *, log: LogSink = NULL_LOG,
) -> list[DimensionResult]:
    """``read_run_data`` with the same error tolerance the LRU fetcher applies."""
    try:
        return read_run_data(reports_root, project, run_id)
    except (OSError, ValueError, KeyError) as exc:
        log.warning(f"read_run_data failed for {run_id}: {exc}")
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


def read_all_run_data(
    reports_root: Path, project: str, run_infos: list[RunInfo],
    get_run_data: Callable[[str], list[DimensionResult]] | None = None,
    get_run_slim: Callable[[str], list[DimensionResult]] | None = None,
) -> tuple[dict[str, DimensionResult], dict[str, DimensionResult], list[DimensionResult]]:
    """Build accumulated data structures from a walk over *run_infos* (newest first).

    With *get_run_slim* the walk runs on findings-free dimensions and only the
    winning dimensions are re-read in full; without it the walk reads every run
    in full, as it always did.
    """
    buckets = _DimensionBuckets()
    _fetch_full = get_run_data or (lambda rid: read_run_data(reports_root, project, rid))
    _fetch = get_run_slim or _fetch_full

    for run_idx_i, run_info in enumerate(run_infos):
        for dim in _fetch(run_info.run_id):
            _classify_dimension(dim, run_info.run_id, run_info, run_idx_i == 0, buckets)

    if get_run_slim is not None:
        _hydrate_latest_dimensions(buckets, _fetch_full)

    return (
        buckets.latest_by_dimension,
        buckets.prev_occurrence,
        list(buckets.prev_run_latest_map.values()),
    )
