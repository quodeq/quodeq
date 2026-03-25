"""Shared LRU cache factory for dimension fetchers."""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from quodeq.adapters.fs.report_parser import read_run_data
from quodeq.core.types import DimensionResult

_logger = logging.getLogger(__name__)


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

    Uses a per-key event to ensure only one thread performs the I/O for a
    given cache miss, while other threads wait on the result.
    """
    _inflight: dict[tuple, threading.Event] = {}

    def get_run_dimensions(run_id: str) -> list[DimensionResult]:
        key = (reports_root, project, run_id)

        with lock:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
            existing_event = _inflight.get(key)
            if existing_event is not None:
                waiter = existing_event
            else:
                waiter = None
                _inflight[key] = threading.Event()

        # Another thread is already fetching this key — wait for it
        if waiter is not None:
            waiter.wait(timeout=30)
            with lock:
                return list(cache.get(key, []))

        # We are the fetcher for this key
        try:
            data = read_run_data(reports_root, project, run_id)
        except (OSError, ValueError) as exc:
            _logger.warning("Failed to read run data for %s/%s: %s", project, run_id, exc)
            data = []

        with lock:
            if data:
                cache[key] = data
                cache.move_to_end(key)
                while len(cache) > max_size:
                    cache.popitem(last=False)
            event = _inflight.pop(key, None)

        if event is not None:
            event.set()

        return data

    return get_run_dimensions
