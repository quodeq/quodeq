"""process_dimension_with_cache — files_read accounting.

Split from test_dimension_runner.py (further split out of
test_dimension_runner_cache_hits.py to stay under the file-size cap).
files_read reflects analyzed count, not input list size.

Pre-fix, every callsite of parse_evidence_from_jsonl in
process_dimension_with_cache passed ``files_read=len(files)``. That
made coverage % (computed downstream as files_read / source_file_count)
always 100% even when the run only finished a fraction of its files —
e.g. a deadline-truncated flexibility run that analyzed 850/3037 files
scored "6.6/Adequate" on a dashboard that couldn't tell it was partial.

The honest signal: files_read = cache hits + dispatch files whose
most recent file_done marker is "ok". Files with file_done="error"
(worker crashed, token-out) or no marker at all are NOT counted —
their analysis was incomplete, the cache has no entry for them, and
the next run will re-dispatch.

Shared scaffolding lives in tests/analysis/cache/conftest.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.cache import CacheEntry, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from tests.analysis.cache.conftest import (
    FakeDispatcher,
    _make_callbacks,
    _make_ctx,
    _make_dummy_evidence,
    _setup,
)


class TestFilesReadReflectsAnalyzedCount:
    """files_read on the returned Evidence must equal the number of source
    files reproducible from cache at run end — NOT len(input_files)."""

    def test_files_read_equals_total_when_all_cache_hits(
        self, tmp_path: Path, cache,
    ):
        """All-hits short-circuit: every input file is a cache hit.
        files_read must equal len(files)."""
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})

        # Pre-populate cache for every input file.
        for f in ["a.py", "b.py", "c.py"]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1,
                findings=[{"file": f, "line": 1, "t": "violation", "w": f"v-{f}"}],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        dispatcher = FakeDispatcher(src)
        ev = process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        assert dispatcher.calls == [], "all-hits path must not dispatch"
        assert ev is not None
        assert ev.files_read == 3, (
            f"all-hits run must report files_read=3, got {ev.files_read}"
        )

    def test_files_read_equals_hits_plus_ok_dispatches(
        self, tmp_path: Path, cache,
    ):
        """3 source files: 1 cache hit, 1 dispatches with file_done='ok',
        1 dispatches with file_done='error'. Expect files_read=2 (hit + ok).
        """
        config, src = _setup(
            tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"},
        )

        # Pre-seed cache for a.py only — b.py and c.py are misses.
        key_a = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key_a, CacheEntry(
            key=key_a, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "cached-a"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        def mixed_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
            # Misses are restricted by the file filter to {b.py, c.py}.
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                # b.py completes with ok marker — counts toward files_read.
                out.write(json.dumps({
                    "file": "b.py", "line": 1, "t": "violation", "w": "fresh-b",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "b.py", "status": "ok",
                }) + "\n")
                # c.py errors out — must NOT count toward files_read.
                out.write(json.dumps({
                    "_marker": "file_done", "file": "c.py",
                    "status": "error", "reason": "token_limit",
                }) + "\n")
            return _make_dummy_evidence(files_read=2)

        ev = process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=mixed_dispatcher,
        )

        assert ev is not None
        # a.py = cache hit (1). b.py = ok dispatch (1). c.py = errored (0).
        assert ev.files_read == 2, (
            f"expected files_read=2 (hit + ok), got {ev.files_read}; "
            f"source_file_count={ev.source_file_count}"
        )
        assert ev.source_file_count == 3, (
            f"source_file_count must equal len(input files) = 3, "
            f"got {ev.source_file_count}"
        )

    def test_files_read_when_dispatch_returns_none_with_carries(
        self, tmp_path: Path, cache,
    ):
        """Dispatch returns None but cached findings exist — the
        ``classify.cached_findings and jsonl.exists()`` branch must also
        use the computed files_read (= just the cache hits, since no
        dispatched files have ok markers)."""
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Pre-populate a.py only.
        key_a = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key_a, CacheEntry(
            key=key_a, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "cached-a"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        # Dispatch returns None (no fresh findings, no markers written).
        def failing_dispatcher(*args, **kwargs):
            return None

        ev = process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=failing_dispatcher,
        )

        assert ev is not None, (
            "dispatch returned None but cached findings should still produce "
            "Evidence via the pre-written JSONL"
        )
        # Only a.py is reproducible — b.py's dispatch produced no ok marker.
        assert ev.files_read == 1, (
            f"expected files_read=1 (just the cache hit), got {ev.files_read}"
        )
