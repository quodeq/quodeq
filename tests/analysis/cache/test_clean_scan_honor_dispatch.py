"""Clean-scan honoring — process_dimension_with_cache dispatch + invalidation.

Split from test_clean_scan_honor.py: process_dimension_with_cache bypasses
cache reads when incremental=False, dispatches all files, and writes fresh
results back to the cache. Also covers the "I want fresh" invalidation
guarantee: a clean scan deletes the (file, dim) cache entries up front, so
a cancelled clean scan never leaves ghost entries from before.

Background: prior to this fix, a clean scan only set bypass_reads=True (so
the in-flight run ignored cache hits) but left existing entries alone. If
the user cancelled the clean scan mid-flight and re-ran without --clean,
the prior entries the user wanted refreshed were still hits, producing the
surprising "instant complete" behaviour.

Shared scaffolding (including the _setup_cache_with_hits/_callbacks
helpers that keep these tests short) lives in
tests/analysis/cache/_clean_scan_honor_fixtures.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.cache import CacheEntry, LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.core.evidence.model import Evidence

from tests.analysis.cache._clean_scan_honor_fixtures import (  # noqa: F401 -- cache is a pytest fixture
    _callbacks,
    _make_ctx,
    _setup,
    _setup_cache_with_hits,
    cache,
)


class TestDispatchBypassesCacheOnCleanScan:
    def test_clean_scan_dispatches_all_files_despite_full_cache(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config, _ = _setup_cache_with_hits(
            tmp_path, cache, {"a.py": "x", "b.py": "y"}, "security", ["a.py", "b.py"],
        )

        dispatched_files: list[str] = []
        def fake_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
            files = sorted(cfg.options.incremental_file_filter or set())
            dispatched_files.extend(files)
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                for f in files:
                    out.write(json.dumps({
                        "file": f, "line": 1, "t": "violation", "w": f"fresh-{f}",
                    }) + "\n")
                    out.write(json.dumps({
                        "_marker": "file_done", "file": f, "status": "ok",
                    }) + "\n")
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=len(files), files_read=len(files),
                coverage_pct=100.0, principles={},
            )

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _callbacks(), cache=cache,
            dispatcher=fake_dispatcher,
        )

        # All files re-dispatched, NOT served from cache.
        assert sorted(dispatched_files) == ["a.py", "b.py"]

    def test_clean_scan_still_writes_fresh_results_to_cache(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Clean scan bypasses reads but writes — the cache stays current."""
        config, _ = _setup(tmp_path, {"a.py": "x"}, incremental=False)
        # Pre-populate with a stale entry that should be overwritten.
        old_key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(old_key, CacheEntry(
            key=old_key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "stale"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        def fake_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "file": "a.py", "line": 1, "t": "violation", "w": "fresh",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "a.py", "status": "ok",
                }) + "\n")
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0,
                principles={},
            )

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _callbacks(), cache=cache,
            dispatcher=fake_dispatcher,
        )

        # Cache entry was overwritten with the fresh dispatch result.
        entry = cache.get(old_key)
        assert entry is not None
        assert any(f.get("w") == "fresh" for f in entry.findings)
        assert all(f.get("w") != "stale" for f in entry.findings)


class TestCleanScanInvalidates:
    def test_clean_scan_deletes_entries_for_this_dim_files(
        self, tmp_path: Path, cache,
    ):
        """Pre-populated entries are gone after process_dimension_with_cache
        runs with incremental=False, even if the dispatch is short-circuited."""
        config, src = _setup_cache_with_hits(
            tmp_path, cache, {"a.py": "x", "b.py": "y"}, "security", ["a.py", "b.py"],
        )

        # Sanity: entries exist before.
        for f in ("a.py", "b.py"):
            assert cache.get(build_cache_key_for_file(config, f, "security")) is not None

        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            # Worker emits a marker for a.py only -- b.py is "abandoned"
            # mid-flight (simulating a cancel after a finished).
            with jsonl.open("w") as out:
                out.write(json.dumps({"file": "a.py", "line": 1, "t": "violation", "w": "fresh-a"}) + "\n")
                out.write(json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n")
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=2, files_read=1, coverage_pct=50.0, principles={},
            )

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _callbacks(), cache=cache,
            dispatcher=fake_dispatch,
        )

        # a.py: re-dispatched, ok marker, repopulated under same key with FRESH content.
        a_entry = cache.get(build_cache_key_for_file(config, "a.py", "security"))
        assert a_entry is not None, "a.py should be re-cached after clean-scan"
        assert any(f.get("w") == "fresh-a" for f in a_entry.findings)
        assert all(f.get("w") != "cached-a.py" for f in a_entry.findings), (
            "stale pre-clean-scan finding leaked through -- the wipe-then-rewrite contract is broken"
        )

        # b.py: invalidated up front, never got an ok marker -- entry is GONE.
        b_entry = cache.get(build_cache_key_for_file(config, "b.py", "security"))
        assert b_entry is None, (
            "stale b.py entry survived a clean-scan that never re-completed it -- "
            "next non-clean run would short-circuit on the ghost entry"
        )

    def test_incremental_run_does_not_invalidate(
        self, tmp_path: Path, cache,
    ):
        """Sanity: invalidation is gated on bypass_reads. A normal
        incremental run that happens to find no hits MUST NOT delete
        anything."""
        config, src = _setup_cache_with_hits(
            tmp_path, cache, {"a.py": "x"}, "security", ["a.py"], incremental=True,
        )
        key_before = build_cache_key_for_file(config, "a.py", "security")
        entry_before = cache.get(key_before)
        assert entry_before is not None

        def noop_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0, principles={},
            )

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _callbacks(), cache=cache,
            dispatcher=noop_dispatch,
        )

        # All-hits path; entry survives untouched.
        entry_after = cache.get(key_before)
        assert entry_after is not None
        assert any(f.get("w") == "cached-a.py" for f in entry_after.findings)
