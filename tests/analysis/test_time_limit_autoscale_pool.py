"""Tests for how launch_pool's deadline and RunConfig reach the pool it builds.

The auto-scaled/extended deadline computed for a dim's pool launch (see
test_time_limit_autoscale.py for the scaling math itself) and the run-scoped
RunConfig must both flow, unchanged, into the AnalysisConfig each subagent
receives -- these tests pin that wiring, plus the pool_factory seam
launch_pool exposes for callers that need to substitute a fake pool.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from quodeq.analysis.run_types import AnalysisOptions, RunConfig


class TestLaunchPoolExtendsDeadline:
    def test_launch_pool_flows_extended_deadline_into_pool(self, tmp_path):
        """The AnalysisConfig handed to the pool must carry the EXTENDED
        deadline, not the stale pre-scale one, so worker drain checks and
        the run deadline agree on a single number. Only the AUTO-SCALED
        budget (time_limit=None) may ratchet; the deadline here comes from
        an outer caller."""
        from quodeq.analysis.subagents import _pool_launcher

        original = time.monotonic() + 60
        config = RunConfig(
            src=tmp_path,
            language="python",
            options=AnalysisOptions(deadline_at=original, time_limit=None),
        )
        params = _pool_launcher.LaunchPoolParams(
            evidence_dir=tmp_path,
            queue_path=tmp_path / "queue.json",
            prompt="p",
            all_files=[f"f{i}.py" for i in range(600)],  # scales to 7200s
        )
        captured = {}

        def _fake_pool(*, paths, options, config):
            captured["config"] = config
            pool = MagicMock()
            pool.run.return_value = []
            return pool

        with patch.object(_pool_launcher, "SubagentPool", side_effect=_fake_pool), \
             patch.object(_pool_launcher, "get_ai_cmd", return_value="ollama"), \
             patch("quodeq.analysis.subagents._pool_launcher.emit_marker"):
            _pool_launcher.launch_pool(config, "dim-x", params)

        assert config.options.deadline_at > original
        assert captured["config"].deadline_at == config.options.deadline_at

    def test_explicit_budget_never_extends_deadline(self, tmp_path):
        """An explicit time_limit is a HARD CAP on the whole run. Each
        dim's pool launch must NOT ratchet the run deadline forward by a
        fresh full budget, or a 1h run becomes '1h after the LAST dim
        launch' (observed: 1h budget, deadline pushed 43min
        past start+1h and still climbing at dim 5/6)."""
        from quodeq.analysis.subagents import _pool_launcher

        # Mid-run: most of the 3600s budget is already spent.
        original = time.monotonic() + 100
        config = RunConfig(
            src=tmp_path,
            language="python",
            options=AnalysisOptions(deadline_at=original, time_limit=3600),
        )
        params = _pool_launcher.LaunchPoolParams(
            evidence_dir=tmp_path,
            queue_path=tmp_path / "queue.json",
            prompt="p",
            all_files=[f"f{i}.py" for i in range(600)],
        )

        def _fake_pool(*, paths, options, config):
            pool = MagicMock()
            pool.run.return_value = []
            return pool

        with patch.object(_pool_launcher, "SubagentPool", side_effect=_fake_pool), \
             patch.object(_pool_launcher, "get_ai_cmd", return_value="ollama"), \
             patch("quodeq.analysis.subagents._pool_launcher.emit_marker") as marker:
            _pool_launcher.launch_pool(config, "dim-x", params)

        assert config.options.deadline_at == original
        assert "deadline_extended" not in [c.args[0] for c in marker.call_args_list]


class TestLaunchPoolCarriesRunConfig:
    def test_pool_config_shares_the_run_config_and_its_owners(self, tmp_path):
        """``_build_pool_config`` must hand every agent's AnalysisConfig the
        SAME RunConfig instance (not a copy), so the run-scoped drop counter
        and MCP registry stay shared across pool worker threads -- see
        ``RunConfig.drop_counter``/``mcp_registry``.

        Imports through the public runner re-export and string patch targets
        rather than the private _pool_launcher module, per the private-import
        ratchet -- see TestLaunchPoolInjectedFactory below."""
        from quodeq.analysis.subagents.runner import LaunchPoolParams, launch_pool

        config = RunConfig(
            src=tmp_path, language="python",
            options=AnalysisOptions(deadline_at=None, time_limit=600),
        )
        params = LaunchPoolParams(
            evidence_dir=tmp_path,
            queue_path=tmp_path / "queue.json",
            prompt="p",
        )
        captured = {}

        def _fake_pool(*, paths, options, config):
            captured["config"] = config
            pool = MagicMock()
            pool.run.return_value = []
            return pool

        with patch("quodeq.analysis.subagents._pool_launcher.SubagentPool", side_effect=_fake_pool), \
             patch("quodeq.analysis.subagents._pool_launcher.get_ai_cmd", return_value="ollama"), \
             patch("quodeq.analysis.subagents._pool_launcher.emit_marker"):
            launch_pool(config, "dim-x", params)

        assert captured["config"].run_config is config
        assert captured["config"].run_config.drop_counter is config.drop_counter
        assert captured["config"].run_config.mcp_registry is config.mcp_registry


class TestLaunchPoolInjectedFactory:
    def test_uses_injected_pool_factory_instead_of_the_concrete_subagent_pool(self, tmp_path):
        """pool_factory is a call-time seam: when set, launch_pool must build
        the pool through it instead of the concrete SubagentPool, and the
        existing patch.object(_pool_launcher, "SubagentPool") tests must keep
        biting on the default (unset) path -- see TestLaunchPoolExtendsDeadline.
        Imports through the public runner re-export and string patch targets
        rather than the private _pool_launcher module, per the private-import
        ratchet."""
        from quodeq.analysis.subagents.runner import LaunchPoolParams, launch_pool

        config = RunConfig(
            src=tmp_path, language="python",
            options=AnalysisOptions(deadline_at=None, time_limit=600),
        )
        params = LaunchPoolParams(
            evidence_dir=tmp_path, queue_path=tmp_path / "queue.json", prompt="p",
        )
        built_with: list = []

        class _FakePool:
            def __init__(self, *, paths, options, config):
                built_with.append((paths, options, config))

            def run(self):
                return ["fake-result"]

        # SubagentPool itself must not be touched: patch it to explode so a
        # regression that falls back to the concrete class fails loudly.
        with patch(
            "quodeq.analysis.subagents._pool_launcher.SubagentPool",
            side_effect=AssertionError("the concrete SubagentPool must not be built"),
        ), patch(
            "quodeq.analysis.subagents._pool_launcher.get_ai_cmd", return_value="ollama",
        ):
            pool, results = launch_pool(
                config, "dim-x", params, pool_factory=_FakePool,
            )

        assert len(built_with) == 1
        assert isinstance(pool, _FakePool)
        assert results == ["fake-result"]
