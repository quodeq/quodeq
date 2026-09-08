"""Bounds on ``HashCache``: each map is an LRU capped by its capacity.

The module-default instance lives as long as the dashboard/API server, so
without a cap it would keep one entry per ``(path, size, mtime_ns)`` ever
seen across every project that process scans. These tests pin the wiring:
each map honours its own capacity and evicts through the shared ``LRUDict``
(whose recency rules live in tests/shared/test_lru.py), ``None`` is a real
cached value (unreadable file), and ``reset`` still empties every map.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quodeq.analysis import fingerprint
from quodeq.analysis.fingerprint import HashCache


def _touch(tmp_path: Path, name: str) -> tuple[Path, int, int]:
    path = tmp_path / name
    path.write_text(name)
    st = path.stat()
    return path, st.st_size, st.st_mtime_ns


def _file_reads(cache: HashCache, *entries: tuple[Path, int, int]) -> int:
    """Real ``_hash_file`` reads that looking up *entries* through *cache* costs."""
    with patch.object(fingerprint, "_hash_file", wraps=fingerprint._hash_file) as spy:
        for entry in entries:
            cache.file_hash(*entry)
    return spy.call_count


def test_file_hash_evicts_least_recent_past_capacity(tmp_path: Path):
    cache = HashCache(file_capacity=2)
    a, b, c = (_touch(tmp_path, n) for n in "abc")
    assert _file_reads(cache, a, b, c) == 3
    # a was coldest when c arrived, so only a is gone.
    assert _file_reads(cache, b, c) == 0
    assert _file_reads(cache, a) == 1


def test_file_hash_caches_none_for_unreadable_path(tmp_path: Path):
    cache = HashCache(file_capacity=2)
    missing = (tmp_path / "missing", 0, 0)
    assert cache.file_hash(*missing) is None
    assert _file_reads(cache, missing) == 0


def test_override_and_params_maps_are_bounded_independently(tmp_path: Path):
    cache = HashCache(override_capacity=1, params_capacity=1)
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    with patch.object(
        fingerprint, "_compute_override_hash", wraps=fingerprint._compute_override_hash,
    ) as overrides:
        for root in (root_a, root_b, root_a):
            cache.override_hash(root, 1, 1)
    assert overrides.call_count == 3  # capacity 1: a is evicted by b, then recomputed
    with patch.object(
        fingerprint, "_compute_dimension_params", wraps=fingerprint._compute_dimension_params,
    ) as params:
        for compiled in (root_a / "x.json", root_b / "x.json", root_a / "x.json"):
            cache.dimension_params_state(compiled, 1, 1, None, 0, 0)
    assert params.call_count == 3


def test_reset_empties_every_map(tmp_path: Path):
    cache = HashCache(file_capacity=4)
    a = _touch(tmp_path, "a")
    _file_reads(cache, a)
    cache.override_hash(tmp_path, 1, 1)
    cache.dimension_params_state(tmp_path / "x.json", 1, 1, None, 0, 0)
    cache.reset()
    assert _file_reads(cache, a) == 1
    with patch.object(
        fingerprint, "_compute_override_hash", wraps=fingerprint._compute_override_hash,
    ) as overrides, patch.object(
        fingerprint, "_compute_dimension_params", wraps=fingerprint._compute_dimension_params,
    ) as params:
        cache.override_hash(tmp_path, 1, 1)
        cache.dimension_params_state(tmp_path / "x.json", 1, 1, None, 0, 0)
    assert overrides.call_count == 1
    assert params.call_count == 1
