"""process_dimension_with_cache — dispatch wiring and carry ordering.

Split from test_dimension_runner.py: the DimensionRunner -> cache-runner
routing smoke test, the dispatch-keys sidecar, carried-vs-fresh finding
ordering in the merged JSONL, and cache-replayed findings reaching
events.jsonl. Shared scaffolding lives in tests/analysis/cache/conftest.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.cache import CacheEntry, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from tests.analysis.cache.conftest import (
    FakeDispatcher,
    _make_callbacks,
    _make_ctx,
    _make_dummy_evidence,
    _setup,
)


class TestWiring:
    def test_dimension_runner_routes_to_cache_runner(
        self, tmp_path: Path,
    ):
        """V2 is the canonical path: DimensionRunner.run always routes
        through process_dimension_with_cache."""
        from quodeq.analysis.dimension_runner import DimensionRunner

        config, src = _setup(tmp_path, {"a.py": "x"})

        called = {"hit": False}
        def fake_cache(config, dim_id, idx, ctx, callbacks, cache=None, **_):
            called["hit"] = True
            return _make_dummy_evidence(files_read=1)

        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            new=fake_cache,
        ):
            DimensionRunner().run(config, "security", 1, _make_ctx(), emit_log=False)

        assert called["hit"] is True


class TestDispatchKeysSidecar:
    def test_sidecar_written_with_miss_keys(self, tmp_path: Path, cache):
        from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        dispatcher = FakeDispatcher(src)
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        sidecar = (config.work_dir or config.src) / "security_dispatch_keys.json"
        assert sidecar.is_file()
        keys = json.loads(sidecar.read_text())
        expected_keys = {
            "a.py": build_cache_key_for_file(config, "a.py", "security"),
            "b.py": build_cache_key_for_file(config, "b.py", "security"),
        }
        assert keys == expected_keys

    def test_sidecar_skipped_when_all_hits(self, tmp_path: Path, cache):
        """All-hits short-circuit returns before reaching the dispatch path,
        so no sidecar is written. Discard for an all-hits dim has nothing
        to wipe anyway."""
        from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
        config, src = _setup(tmp_path, {"a.py": "x"})
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "v"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        dispatcher = FakeDispatcher(src)
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        assert dispatcher.calls == []  # confirm we hit the all-hits path
        sidecar = (config.work_dir or config.src) / "security_dispatch_keys.json"
        assert not sidecar.exists()


# ============================================================
# Carry order: cached findings appear FIRST in the JSONL
# ============================================================
#
# Pre-fix, cached findings were appended AFTER dispatch wrote its fresh
# findings, producing two effects users complained about:
#  1. The merged JSONL ordered fresh-then-cached, so the final report
#     read "new findings, then carries" -- the opposite of how a user
#     thinks about it ("carries are foundation, fresh is on top").
#  2. The dispatcher's internal dedup ran BEFORE we appended cached
#     findings, producing two log lines like "Deduplicated ...: 27"
#     followed by "Deduplicated ...: 55", visibly confusing.
#
# Now: cached findings are pre-written to the JSONL BEFORE dispatch.
# Dispatch's internal dedup sees the merged set in one pass.


class TestCarryOrder:
    def test_cached_findings_appear_before_fresh(self, tmp_path: Path, cache):
        """Pre-populate cache for one file. Dispatch a different file. The
        JSONL should have the cached file's findings BEFORE the dispatched
        file's findings (carries first, then fresh)."""
        from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache

        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Cache a.py with a recognizable finding.
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation",
                       "w": "carry-a", "p": "P1", "d": "security",
                       "req": "X-1", "severity": "minor",
                       "snippet": "x", "reason": "r"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        # b.py is a miss -- fake dispatcher writes a fresh finding for it.
        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "file": "b.py", "line": 1, "t": "violation",
                    "w": "fresh-b", "p": "P2", "d": "security",
                    "req": "X-2", "severity": "minor",
                    "snippet": "y", "reason": "r",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "b.py", "status": "ok",
                }) + "\n")
            return _make_dummy_evidence(files_read=1)

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(),
            _make_callbacks(), cache=cache,
            dispatcher=fake_dispatch,
        )

        jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
        lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
        # Filter to actual finding lines (not markers).
        findings = [ln for ln in lines if "_marker" not in ln]
        # Carry comes first; fresh comes second.
        assert findings[0]["w"] == "carry-a", (
            f"expected carry-a first, got {[f.get('w') for f in findings]}"
        )
        assert any(f.get("w") == "fresh-b" for f in findings), (
            "fresh dispatch finding missing from JSONL"
        )
        # Specifically: the carry comes before the fresh in JSONL order.
        carry_idx = next(i for i, f in enumerate(findings) if f.get("w") == "carry-a")
        fresh_idx = next(i for i, f in enumerate(findings) if f.get("w") == "fresh-b")
        assert carry_idx < fresh_idx, (
            f"carry (index {carry_idx}) should appear before fresh (index {fresh_idx})"
        )


class TestCachedFindingsReachEventLog:
    """Pin that cache-replayed findings land in ``events.jsonl`` as
    ``JUDGMENT_CREATED`` events, not only in the per-dim JSONL.

    Without this, an incremental run's SQL projection (which reads
    ``events.jsonl``) sees only the freshly-dispatched findings — the
    dashboard grade tables disagree with the CLI's JSON output because
    they're scoring different sets of findings. The user reported this as
    "flexibility shows 7.7 in the CLI but 9.0 in the UI" on a real
    incremental run; the gap was exactly the cache-restored findings.
    """

    def _read_events(self, events_log: Path) -> list[dict]:
        if not events_log.exists():
            return []
        out = []
        for line in events_log.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out

    def test_all_hits_run_emits_judgment_events_for_cache_replay(
        self, tmp_path: Path, cache,
    ):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Pre-populate cache for both files so the run short-circuits dispatch.
        for f in ["a.py", "b.py"]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1,
                findings=[{
                    "file": f, "line": 7, "t": "violation",
                    "w": f"cached-{f}", "p": "Confidentiality", "d": "security",
                    "req": f"S-CON-{f}", "severity": "minor",
                    "snippet": "s", "reason": "r",
                }],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        dispatcher = FakeDispatcher(src)
        # events.jsonl lives at <evidence_dir>/.. which is <work_dir>/..
        # The runner derives this from the per-dim JSONL path internally.
        events_log = (config.work_dir or config.src).parent / "events.jsonl"

        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        assert dispatcher.calls == [], "all-hits path must not dispatch"

        events = self._read_events(events_log)
        # Every cached finding must produce a JUDGMENT_CREATED event so the
        # SQL projection sees it. Without the fix this list would be empty.
        judgments = [e for e in events if e.get("event_type") == "JUDGMENT_CREATED"]
        files_in_events = {e["payload"]["file"] for e in judgments}
        assert files_in_events == {"a.py", "b.py"}, (
            f"events.jsonl must contain a JUDGMENT_CREATED per cached finding; "
            f"got {files_in_events}"
        )

    def test_partial_run_emits_judgment_events_for_carried_findings(
        self, tmp_path: Path, cache,
    ):
        """Mixed run: one cached hit (a.py) + one dispatched miss (b.py).

        The cached carry was the silently-dropped path — pin that it shows
        up in events.jsonl alongside the dispatcher's own emit.
        """
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{
                "file": "a.py", "line": 1, "t": "violation",
                "w": "carry-a", "p": "Confidentiality", "d": "security",
                "req": "S-CON-A", "severity": "minor",
                "snippet": "x", "reason": "r",
            }],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        events_log = (config.work_dir or config.src).parent / "events.jsonl"

        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
            # The dispatcher in production routes through FindingsRouter,
            # which emits events. This fake only writes JSONL — we're
            # specifically testing the cache-replay side.
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "file": "b.py", "line": 1, "t": "violation",
                    "w": "fresh-b", "p": "Confidentiality", "d": "security",
                    "req": "S-CON-B", "severity": "minor",
                    "snippet": "y", "reason": "r",
                }) + "\n")
            return _make_dummy_evidence(files_read=1)

        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=fake_dispatch,
        )

        events = self._read_events(events_log)
        carry_files = {
            e["payload"]["file"] for e in events
            if e.get("event_type") == "JUDGMENT_CREATED"
        }
        assert "a.py" in carry_files, (
            f"cached carry for a.py must emit a JUDGMENT_CREATED event; "
            f"got {carry_files}"
        )
