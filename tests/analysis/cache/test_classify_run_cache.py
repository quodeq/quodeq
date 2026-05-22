"""Per-run stash for ``classify_files_via_cache``.

The pipeline classifies files twice per dim:

1. Upfront in ``_persist_dim_estimates`` to write ``dim_estimates.json``
   so the dashboard can render the total before any dim starts.
2. Again inside ``cache/dimension_runner.process_dimension_with_cache``
   for the actual hit/miss dispatch.

Both calls produce identical results in the common path (incremental
mode, no diff filter, same file list). After the manifest fix in #539
each pass is fast, but they are still pure redundant work — three
thousand SHA-256s + three thousand ``cache.get`` calls performed twice.

The fix is a small per-``RunConfig`` cache: when the run activates it
(by setting ``_classify_cache = {}``), ``classify_files_via_cache``
populates the dict on the first call for a given ``dim_id`` and short-
circuits the second call when the file list still matches.

The cache MUST NOT short-circuit when:
  - The two calls disagree on the file list (diff mode narrows the
    second call's input).
  - ``bypass_reads=True`` (clean-scan: the dim runner deletes entries
    immediately before this call, so the upfront classify is stale).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    classify_files_via_cache,
)


def _write_files(root: Path, contents: dict[str, str]) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return sorted(contents.keys())


def _make_config(src: Path) -> RunConfig:
    return RunConfig(
        src=src, language="python", work_dir=src,
        options=AnalysisOptions(subagent_model="m"),
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


def test_classify_populates_run_cache_when_attached(tmp_path: Path, cache: LocalFileBackend):
    """When ``_classify_cache`` is an empty dict, the first call stores
    the (files, result) pair under the dimension id.
    """
    src = tmp_path / "src"
    files = _write_files(src, {"a.py": "x", "b.py": "y"})
    config = _make_config(src)
    config._classify_cache = {}

    result = classify_files_via_cache(config, "security", files, cache)

    assert "security" in config._classify_cache
    stashed_files, stashed_result = config._classify_cache["security"]
    assert stashed_files == tuple(files)
    assert stashed_result is result


def test_classify_reuses_stashed_result_on_second_call(tmp_path: Path, cache: LocalFileBackend):
    """A second call with the same (dim, files) returns the stashed
    object directly — no fresh disk I/O against the cache backend.
    """
    src = tmp_path / "src"
    files = _write_files(src, {"a.py": "x", "b.py": "y"})
    config = _make_config(src)
    config._classify_cache = {}

    first = classify_files_via_cache(config, "security", files, cache)

    # Sentinel: after the first call, replacing ``cache`` with one that
    # would error on any access proves the second call short-circuits
    # before touching the backend.
    class ExplodingCache:
        def get(self, key):  # pragma: no cover - must never be invoked
            raise AssertionError(
                "classify hit the cache backend instead of returning the stashed result",
            )

    second = classify_files_via_cache(config, "security", files, ExplodingCache())  # type: ignore[arg-type]
    assert second is first


def test_classify_ignores_stash_when_files_differ(tmp_path: Path, cache: LocalFileBackend):
    """Diff mode narrows the dim runner's file list. The stash from the
    upfront pass (all files) must NOT be reused for the narrower call.
    """
    src = tmp_path / "src"
    full = _write_files(src, {"a.py": "x", "b.py": "y", "c.py": "z"})
    narrow = ["a.py"]
    config = _make_config(src)
    config._classify_cache = {}

    classify_files_via_cache(config, "security", full, cache)
    result = classify_files_via_cache(config, "security", narrow, cache)

    # The narrower call's result references only the narrower files.
    assert set(result.miss_keys.keys()) == {"a.py"}
    assert len(result.misses) == 1


def test_classify_does_not_use_stash_when_bypass_reads_true(tmp_path: Path, cache: LocalFileBackend):
    """Clean-scan mode (``bypass_reads=True``) means the dim runner has
    already wiped this dim's entries from the cache. The upfront
    classify's hits are stale; the second call must redo the work and
    force every file into the misses bucket.
    """
    src = tmp_path / "src"
    files = _write_files(src, {"a.py": "x"})
    config = _make_config(src)
    config._classify_cache = {}

    first = classify_files_via_cache(config, "security", files, cache, bypass_reads=False)
    second = classify_files_via_cache(config, "security", files, cache, bypass_reads=True)

    # ``bypass_reads`` forces every file into ``misses`` regardless of
    # any cached hits the first call recorded.
    assert second is not first
    assert second.misses == list(files)


def test_classify_works_without_stash_attached(tmp_path: Path, cache: LocalFileBackend):
    """When ``_classify_cache`` is None (the default), classify behaves
    exactly as before — no stash side effects, no errors.
    """
    src = tmp_path / "src"
    files = _write_files(src, {"a.py": "x"})
    config = _make_config(src)
    assert config._classify_cache is None

    result = classify_files_via_cache(config, "security", files, cache)
    assert isinstance(result, ClassifyResult)
    assert config._classify_cache is None


def test_classify_stash_isolated_per_dimension(tmp_path: Path, cache: LocalFileBackend):
    """Two different dimensions get independent entries; the second
    dim's call must not return the first dim's stash.
    """
    src = tmp_path / "src"
    files = _write_files(src, {"a.py": "x"})
    config = _make_config(src)
    config._classify_cache = {}

    sec_result = classify_files_via_cache(config, "security", files, cache)
    flex_result = classify_files_via_cache(config, "flexibility", files, cache)

    assert "security" in config._classify_cache
    assert "flexibility" in config._classify_cache
    # Different dims produce different miss_keys (cache keys include dimension).
    sec_key = next(iter(sec_result.miss_keys.values()))
    flex_key = next(iter(flex_result.miss_keys.values()))
    assert sec_key != flex_key
