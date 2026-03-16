"""Shared LRU cache factory for dimension fetchers."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from quodeq.adapters.fs.report_parser import read_run_data
from quodeq.core.types import DimensionResult


def make_lru_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[DimensionResult]],
    lock: threading.Lock,
    max_size: int,
) -> Callable[[str], list[DimensionResult]]:
    """Return a callable that fetches dimension data for a run.

    Results are stored in *cache* (LRU, bounded at *max_size* entries) so
    repeated calls within and across requests avoid redundant file reads.
    """
    def get_run_dimensions(run_id: str) -> list[DimensionResult]:
        key = (reports_root, project, run_id)
        with lock:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
        data = read_run_data(reports_root, project, run_id)
        with lock:
            cache[key] = data
            cache.move_to_end(key)
            if len(cache) > max_size:
                cache.popitem(last=False)  # evict oldest
        return data

    return get_run_dimensions
