"""Memoization of ``_hash_prompts_map`` and ``_hash_standards``.

These hashes are computed inside ``build_cache_key_for_file`` for every
(file, dimension) pair. Prompts are identical for the entire run; the
compiled standards JSON is identical for the entire dimension. Re-hashing
them once per file is wasted I/O — on a 3K-file repo that's thousands of
redundant reads of the same handful of bytes.

The cache must be:

1. **Hit on identical inputs** — same call args, no second filesystem read.
2. **Miss on different inputs** — a different ``standards_dir`` or
   ``dimension`` still computes a fresh hash.
3. **Stable across argument forms** — ``Path`` is hashable; the result
   must be the same regardless of whether the caller passes the path as
   a string or a ``Path``.

A single process never swaps the underlying files (each ``quodeq evaluate``
is fresh), so unbounded caching is safe within a run.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis import fingerprint


def _write_compiled_standard(standards_dir: Path, dimension: str, body: str) -> None:
    """Mirror the on-disk layout that ``_hash_standards`` expects."""
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dimension}.json").write_text(body)


@pytest.fixture(autouse=True)
def _clear_fingerprint_caches():
    """Reset the LRU caches before each test so call counts are isolated."""
    # The implementation will define cache_clear hooks on the memoized
    # helpers. Use getattr so this fixture stays valid before and after
    # the impl lands (clearing is a no-op when the cache doesn't exist).
    for name in ("_hash_prompts_map", "_hash_standards"):
        fn = getattr(fingerprint, name, None)
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()
    yield
    for name in ("_hash_prompts_map", "_hash_standards"):
        fn = getattr(fingerprint, name, None)
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()


def test_hash_standards_memoizes_within_dimension(tmp_path: Path):
    """Two calls with the same (standards_dir, dimension) share one read."""
    _write_compiled_standard(tmp_path, "flexibility", '{"rule": "v1"}')

    with patch.object(
        fingerprint, "_hash_file", wraps=fingerprint._hash_file,
    ) as spy:
        first = fingerprint._hash_standards(tmp_path, "flexibility")
        second = fingerprint._hash_standards(tmp_path, "flexibility")

    assert first == second
    assert first is not None
    assert spy.call_count == 1, (
        f"expected one filesystem read across two identical calls, got {spy.call_count}"
    )


def test_hash_standards_does_not_collide_across_dimensions(tmp_path: Path):
    """Different dimensions hash different files — cache must not collide."""
    _write_compiled_standard(tmp_path, "flexibility", '{"rule": "flex"}')
    _write_compiled_standard(tmp_path, "security", '{"rule": "sec"}')

    flex = fingerprint._hash_standards(tmp_path, "flexibility")
    sec = fingerprint._hash_standards(tmp_path, "security")

    assert flex is not None and sec is not None
    assert flex != sec


def test_hash_prompts_map_memoizes_within_run(tmp_path: Path):
    """Repeated calls with no argument hit the default prompts dir once."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "evaluation_rules.md").write_text("hello")
    (prompts / "finding_format.md").write_text("world")

    with patch.object(
        fingerprint, "_hash_file", wraps=fingerprint._hash_file,
    ) as spy:
        first = fingerprint._hash_prompts_map(prompts)
        second = fingerprint._hash_prompts_map(prompts)

    assert first == second
    assert set(first.keys()) == {"evaluation_rules.md", "finding_format.md"}
    # Two .md files × two calls would be 4 reads without memoization.
    assert spy.call_count == 2, (
        f"expected one read per unique prompt file across calls, got {spy.call_count}"
    )


def test_hash_prompts_map_returns_immutable_safe_copy(tmp_path: Path):
    """Callers must not be able to mutate the cached dict for later callers."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "evaluation_rules.md").write_text("hello")

    first = fingerprint._hash_prompts_map(prompts)
    first["evaluation_rules.md"] = "tampered"

    second = fingerprint._hash_prompts_map(prompts)
    assert second["evaluation_rules.md"] != "tampered"


def test_hash_prompts_map_different_dirs_have_independent_caches(tmp_path: Path):
    """Two distinct prompt dirs must not share a cache entry."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    (dir_a / "x.md").write_text("AAA")
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    (dir_b / "x.md").write_text("BBB")

    map_a = fingerprint._hash_prompts_map(dir_a)
    map_b = fingerprint._hash_prompts_map(dir_b)

    assert map_a["x.md"] != map_b["x.md"]
