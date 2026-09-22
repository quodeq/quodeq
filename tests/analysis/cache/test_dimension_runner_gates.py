"""process_dimension_with_cache — the provenance gate on replay.

Split from test_dimension_runner.py: cache-replayed findings must pass
through the same deterministic gates as freshly-dispatched ones (issue
#657). The scope-gate half lives in test_dimension_runner_scope_gate.py.
Shared scaffolding lives in tests/analysis/cache/conftest.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.run_types import RunConfig
from quodeq.analysis.cache import CacheEntry, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
from tests.analysis.cache.conftest import (
    FakeDispatcher,
    _make_callbacks,
    _make_ctx,
    _setup,
)


class TestCacheReplayAppliesProvenanceGate:
    """Issue #657: findings replayed from a pre-#639 cache entry must pass
    through the deterministic provenance gate too.

    The live finding path gates in ``FindingEnricher.enrich()``, but cache
    replay (``_write_findings``) writes cached findings straight to the
    per-dim JSONL and the event log, bypassing ``enrich()``. A stale,
    un-gated ``critical`` R-FT-2 / S-AUT-3 finding produced by an older
    quodeq version would otherwise replay at ``critical`` and inflate the
    grade. Re-gating on the replay write path keeps cached and
    freshly-dispatched findings consistent.
    """

    @staticmethod
    def _cached_critical(file: str, reason: str) -> dict:
        return {
            "file": file, "line": 1, "t": "violation",
            "w": "Unguarded index access", "p": "Fault Tolerance",
            "d": "security", "req": "R-FT-2", "severity": "critical",
            "snippet": "arr[idx]", "reason": reason,
        }

    @staticmethod
    def _findings_in(jsonl: Path) -> list[dict]:
        return [
            json.loads(ln) for ln in jsonl.read_text().splitlines()
            if ln.strip() and "_marker" not in ln
        ]

    def _replay_all_hits(
        self, tmp_path: Path, cache, reason: str,
    ) -> tuple[RunConfig, FakeDispatcher]:
        config, src = _setup(tmp_path, {"a.py": "x"})
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[self._cached_critical("a.py", reason)],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))
        dispatcher = FakeDispatcher(src)
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=dispatcher),
        )
        assert dispatcher.calls == [], "all-hits path must not dispatch"
        return config, dispatcher

    def test_cached_critical_without_external_source_is_downgraded(
        self, tmp_path: Path, cache,
    ):
        # A pre-#639 critical R-FT-2 whose reason names no external ingress
        # source -- "argument" is deliberately NOT a trust-boundary term.
        config, _ = self._replay_all_hits(
            tmp_path, cache,
            "Index derived from a function argument with no bounds check.",
        )

        jsonl = (config.work_dir or config.src) / "security_evidence.jsonl"
        findings = self._findings_in(jsonl)
        assert len(findings) == 1
        assert findings[0]["severity"] == "major", (
            "cache-replayed critical R-FT-2 without an external source must "
            "be downgraded to major by the provenance gate"
        )
        assert findings[0].get("provenance_downgrade") is True

        # The gated severity must also reach the event log -- that's the
        # path the SQL projection / grade reads, so a stale critical here
        # would still inflate the score even after the JSONL was fixed.
        events_log = (config.work_dir or config.src).parent / "events.jsonl"
        events = [
            json.loads(ln) for ln in events_log.read_text().splitlines()
            if ln.strip()
        ] if events_log.exists() else []
        judgments = [e for e in events if e.get("event_type") == "JUDGMENT_CREATED"]
        assert judgments, "cache replay must emit a JUDGMENT_CREATED event"
        assert judgments[0]["payload"]["severity"] == "major", (
            "the gated severity must reach events.jsonl, not the stale critical"
        )

    def test_cached_critical_naming_external_source_is_preserved(
        self, tmp_path: Path, cache,
    ):
        # Same finding, but the reason names a reachable external source --
        # the gate must leave it critical.
        config, _ = self._replay_all_hits(
            tmp_path, cache,
            "Index taken straight from the HTTP request body, unvalidated.",
        )

        jsonl = (config.work_dir or config.src) / "security_evidence.jsonl"
        findings = self._findings_in(jsonl)
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical", (
            "a cache-replayed critical naming an external source must NOT be "
            "downgraded"
        )
        assert "provenance_downgrade" not in findings[0]
