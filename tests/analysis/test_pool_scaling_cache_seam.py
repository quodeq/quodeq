"""Seam for the pool-scaling FileQueue cache: injectable and clearable."""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from quodeq.analysis.subagents import _pool_scaling


def _queue_file(tmp_path: Path) -> Path:
    p = tmp_path / "q.json"
    p.write_text(json.dumps(
        {"version": 1, "pending": [], "taken": [], "max_files_per_agent": 10}
    ))
    return p


def test_get_queue_uses_injected_cache(tmp_path):
    cache: OrderedDict = OrderedDict()
    p = _queue_file(tmp_path)

    q1 = _pool_scaling.get_queue(None, p, cache=cache)
    q2 = _pool_scaling.get_queue(None, p, cache=cache)

    assert q1 is q2
    assert list(cache) == [p]
    assert p not in _pool_scaling._cached_file_queues


def test_clear_cached_queues(tmp_path):
    p = _queue_file(tmp_path)
    _pool_scaling.get_queue(None, p)
    assert p in _pool_scaling._cached_file_queues

    _pool_scaling.clear_cached_queues()

    assert len(_pool_scaling._cached_file_queues) == 0
