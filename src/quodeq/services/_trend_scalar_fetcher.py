"""Scalar fast path of the trend fetcher, cached for the process.

Split from ``trend_fetcher``. Every /scores and /dashboard request walks the
whole history window through this fetcher, so entries outlive the request;
``_scalar_version_for`` keys each one on the inputs that can still change a
finished run's grades.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import DimensionResult
from quodeq.services._dashboard_cache import TREND_SCALAR_CACHE_MAX, shared_trend_scalar_cache
from quodeq.services.cache import DimensionCacheContext, make_lru_dimension_fetcher
from quodeq.shared.validation import validate_path_segment

_Fetcher = Callable[[str], list[DimensionResult]]


def make_scalar_trend_fetcher(
    reports_root: Path, project: str, cacheable_run_ids: set[str] | None,
    read_scalars: Callable[[Path, str, str], list[DimensionResult]],
    *, log: LogSink = NULL_LOG,
) -> _Fetcher:
    """Fast path: scalars through the process-wide trend scalar cache.

    Runs outside *cacheable_run_ids* are memoized for this fetcher only, so
    one request reads an in-progress run once and the next request re-reads it.
    """
    def read_scalars_only(rr: Path, proj: str, run_id: str) -> list[DimensionResult]:
        # Same tolerance as the cached path's disk read: a run that cannot be
        # read is skipped, never a failed request.
        try:
            dims = read_scalars(rr, proj, run_id)
        except (OSError, ValueError, KeyError) as exc:
            log.warning(f"Failed to read run scalars for {proj}/{run_id}: {exc}")
            return []
        return [replace(d, violations=[], compliance=[]) for d in dims]

    cache = shared_trend_scalar_cache()
    ctx = DimensionCacheContext(
        cache=cache.data, lock=cache.lock, max_size=TREND_SCALAR_CACHE_MAX,
        reader=read_scalars_only,
    )
    cached = make_lru_dimension_fetcher(
        reports_root, project, ctx, version_for=_scalar_version_for(reports_root / project),
    )
    if cacheable_run_ids is None:
        return cached
    this_request: dict[str, list[DimensionResult]] = {}

    def fetch(run_id: str) -> list[DimensionResult]:
        if run_id in cacheable_run_ids:
            return cached(run_id)
        if run_id not in this_request:
            this_request[run_id] = read_scalars_only(reports_root, project, run_id)
        return this_request[run_id]

    return fetch


def _log_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _scalar_version_for(project_dir: Path) -> Callable[[str], str]:
    """Per-run cache version for the scalar fast path.

    A finished run's SQL grades are re-derived when its ``events.jsonl`` or the
    project's ``actions.jsonl`` grows, or when ``GRADE_ALGO_VERSION`` changes
    (see ``Projector._detect_staleness``). The version carries the same three
    inputs, so any of those changes produces a new key instead of a stale hit.
    Both logs are append-only, so size is the same signal the projector uses.
    The actions log is read once per fetcher, which is once per request.
    """
    from quodeq.core.scoring import projector_scoring  # noqa: PLC0415
    base = f"scalars:{projector_scoring.GRADE_ALGO_VERSION}:{_log_size(project_dir / 'actions.jsonl')}"

    def version_for(run_id: str) -> str:
        validate_path_segment(run_id)
        return f"{base}:{_log_size(project_dir / run_id / 'events.jsonl')}"

    return version_for
