"""process_dimension_with_cache — the scope gate on replay.

Split from test_dimension_runner_gates.py, which keeps the provenance-gate
half. Shared scaffolding lives in tests/analysis/cache/conftest.py.
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


class TestCacheReplayAppliesScopeGate:
    """The scope gate must be re-applied on the replay
    path too, exactly like the provenance gate is for issue #657.

    ``FindingEnricher.enrich()`` calls ``apply_scope_gate`` right after
    ``apply_provenance_gate`` on the live path, but that method only runs
    once per freshly-dispatched finding -- cache replay writes straight to
    the per-dim JSONL via ``write_findings`` and never touches ``enrich()``.
    Without re-gating here, a ``major`` finding already sitting in a warm
    cache would never be re-capped after the operator declares a tighter
    trust model in ``.quodeq/project-profile.json``, which on a repo with
    warm caches is most findings -- the feature would be largely inert.
    """

    @staticmethod
    def _cached_finding(file: str, req: str, severity: str, reason: str) -> dict:
        return {
            "file": file, "line": 1, "t": "violation",
            "w": "Path built from an unvalidated value", "p": "Access Control",
            "d": "security", "req": req, "severity": severity,
            "snippet": "open(name)", "reason": reason,
        }

    @staticmethod
    def _write_profile(
        src: Path, *, multi_tenant: bool, network_exposure: str,
        deployment_topology: str = "distributed",
    ) -> None:
        profile_dir = src / ".quodeq"
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "project-profile.json").write_text(json.dumps({
            "version": 1,
            "multiTenant": multi_tenant,
            "networkExposure": network_exposure,
            "deploymentTopology": deployment_topology,
        }))

    @staticmethod
    def _findings_in(jsonl: Path) -> list[dict]:
        return [
            json.loads(ln) for ln in jsonl.read_text().splitlines()
            if ln.strip() and "_marker" not in ln
        ]

    @classmethod
    def _replayed_findings(cls, config: RunConfig) -> list[dict]:
        """The findings the replay wrote to the run's security evidence file."""
        return cls._findings_in((config.work_dir or config.src) / "security_evidence.jsonl")

    def _replay_all_hits(
        self, tmp_path: Path, cache, finding: dict,
        *, profile: tuple[bool, str, str] | None,
    ) -> RunConfig:
        config, src = _setup(tmp_path, {"a.py": "x"})
        if profile is not None:
            multi_tenant, network_exposure, deployment_topology = profile
            self._write_profile(
                src, multi_tenant=multi_tenant, network_exposure=network_exposure,
                deployment_topology=deployment_topology,
            )
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[finding],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))
        dispatcher = FakeDispatcher(src)
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=dispatcher),
        )
        assert dispatcher.calls == [], "all-hits path must not dispatch"
        return config

    def test_cached_major_scope_finding_is_capped_under_loopback_single_tenant(
        self, tmp_path: Path, cache,
    ):
        # A cached major S-AUT-3 whose reason names no external or operator
        # source -- the sourceless-path rule's exact target.
        finding = self._cached_finding(
            "a.py", "S-AUT-3", "major",
            "Path built from a filename argument with no bounds check.",
        )
        config = self._replay_all_hits(
            tmp_path, cache, finding,
            profile=(False, "loopback", "distributed"),
        )

        findings = self._replayed_findings(config)
        assert len(findings) == 1
        assert findings[0]["severity"] == "minor", (
            "a cache-replayed major S-AUT-3 finding must be capped to minor "
            "once the project declares a loopback, single-tenant trust model "
            "-- this is exactly the case a warm cache would otherwise hide"
        )
        assert findings[0].get("scope_downgrade", {}).get("rule") == "sourceless_path"

    def test_cached_major_scope_finding_untouched_without_declared_trust_model(
        self, tmp_path: Path, cache,
    ):
        # Same finding, but no .quodeq/project-profile.json -- resolution
        # falls back to CONSERVATIVE, which relaxes nothing.
        finding = self._cached_finding(
            "a.py", "S-AUT-3", "major",
            "Path built from a filename argument with no bounds check.",
        )
        config = self._replay_all_hits(tmp_path, cache, finding, profile=None)

        findings = self._replayed_findings(config)
        assert len(findings) == 1
        assert findings[0]["severity"] == "major", (
            "without a declared trust model the conservative default must "
            "not relax anything"
        )
        assert "scope_downgrade" not in findings[0]

    def test_cached_critical_scope_gated_req_ends_at_minor_after_both_gates(
        self, tmp_path: Path, cache,
    ):
        # Cross-gate ordering: a critical S-AUT-3 naming no source must first
        # be downgraded to major by the provenance gate, and THEN capped to
        # minor by the scope gate -- the scope gate only ever acts on major,
        # so running it before the provenance gate would leave this finding
        # stuck at major (or, worse, unseen at critical). Assert the end
        # state the finding settles at, not an intermediate severity.
        finding = self._cached_finding(
            "a.py", "S-AUT-3", "critical",
            "Path built from a filename argument with no bounds check.",
        )
        config = self._replay_all_hits(
            tmp_path, cache, finding,
            profile=(False, "loopback", "distributed"),
        )

        findings = self._replayed_findings(config)
        assert len(findings) == 1
        assert findings[0]["severity"] == "minor", (
            "a cache-replayed critical S-AUT-3 finding naming no source must "
            "end at minor after passing through both gates in sequence under "
            "a loopback single-tenant model"
        )
        # Both gates must have actually fired, proving the order: the
        # provenance gate moved critical -> major, and the scope gate then
        # moved major -> minor.
        assert findings[0].get("provenance_downgrade") is True
        assert findings[0].get("scope_downgrade", {}).get("rule") == "sourceless_path"

    def test_scope_downgrade_reaches_events_jsonl(
        self, tmp_path: Path, cache,
    ):
        """End-to-end: a cached major finding the scope gate caps on replay
        must carry its rule name all the way into events.jsonl, not just the
        per-dim JSONL -- events.jsonl is what the SQL projection and the
        dashboard actually read. A gap here would fix the JSONL forensic
        record while leaving the dashboard showing an unexplained minor."""
        finding = self._cached_finding(
            "a.py", "S-AUT-3", "major",
            "Path built from a filename argument with no bounds check.",
        )
        config = self._replay_all_hits(
            tmp_path, cache, finding,
            profile=(False, "loopback", "distributed"),
        )

        events_log = (config.work_dir or config.src).parent / "events.jsonl"
        events = [
            json.loads(ln) for ln in events_log.read_text().splitlines()
            if ln.strip()
        ] if events_log.exists() else []
        judgments = [e for e in events if e.get("event_type") == "JUDGMENT_CREATED"]
        assert judgments, "cache replay must emit a JUDGMENT_CREATED event"
        payload_marker = judgments[0]["payload"].get("scope_downgrade")
        assert payload_marker is not None, (
            "scope_downgrade must reach events.jsonl, not just the per-dim JSONL"
        )
        assert payload_marker["rule"] == "sourceless_path"

    def test_cached_major_scalability_finding_is_capped_under_single_host(
        self, tmp_path: Path, cache,
    ):
        # Topology is not in the CacheKey either, so declaring single-host
        # must re-cap an already-cached F-SCL-1 on the next run with no
        # cache miss -- exactly what networkExposure does for S-AUT-3.
        finding = self._cached_finding(
            "a.py", "F-SCL-1", "major",
            "Session state is held in a process-local dict.",
        )
        config = self._replay_all_hits(
            tmp_path, cache, finding,
            profile=(False, "loopback", "single-host"),
        )

        replayed = self._replayed_findings(config)
        assert [f["severity"] for f in replayed] == ["minor"]
        assert replayed[0]["scope_downgrade"]["rule"] == "single_host_topology"
