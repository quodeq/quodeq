"""QUODEQ_FAILURE_STREAK is resolved once per run by the CLI.

The dim runner used to read the override itself at every dimension start;
it now reads only ``AnalysisOptions.failure_streak_threshold``, which the
CLI fills from the environment when it builds the run config.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
from quodeq.analysis.cache.failure_streak import CircuitBreakerError
from tests.analysis.cache.conftest import _make_callbacks, _make_ctx, _make_dummy_evidence, _setup


class TestFailureStreakResolvedOncePerRun:
    def test_cli_resolved_env_trips_the_breaker(self, tmp_path: Path, cache, monkeypatch):
        """QUODEQ_FAILURE_STREAK reaches the breaker through the CLI's run
        config, and a later change to the process env is not re-read."""
        import argparse

        from quodeq.cli import ResolvedInputs, build_run_config
        from quodeq.shared import cancellation
        cancellation.reset()

        monkeypatch.setenv("QUODEQ_FAILURE_STREAK", "2")
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False, max_turns=None,
            max_duration=None, n_subagents=1, pool_budget=None, clean_scan=False,
            legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        cli_options = build_run_config(args, inputs=inputs, evidence_dir=tmp_path).options
        monkeypatch.setenv("QUODEQ_FAILURE_STREAK", "0")  # would disable it if re-read

        config, _src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})
        config = replace(config, options=replace(
            config.options, failure_streak_threshold=cli_options.failure_streak_threshold))
        evidence_dir = config.work_dir or config.src

        def err_dispatcher(config, dim_id, idx, ctx, callbacks, **_):
            jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                for name in ("a.py", "b.py"):
                    out.write(json.dumps({
                        "_marker": "file_done", "file": name,
                        "status": "error", "reason": "token_limit",
                    }) + "\n")
            return _make_dummy_evidence(files_read=2)

        try:
            with pytest.raises(CircuitBreakerError):
                process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=err_dispatcher),
                )
        finally:
            cancellation.reset()
