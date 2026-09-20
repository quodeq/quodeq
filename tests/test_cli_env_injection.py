"""The CLI boundary resolves the run's environment once and passes it on.

``_environ`` is that seam: ``os.environ`` when nothing is injected, and the
injected mapping otherwise — including an empty one, which means "no
variables set" rather than "fall back to the process".
"""
from __future__ import annotations

import argparse
import io
import os

from quodeq._cli_env import _environ


def test_environ_returns_the_injected_mapping(monkeypatch):
    monkeypatch.setenv("FROM_PROCESS", "1")
    assert _environ({"A": "1"}) == {"A": "1"}
    assert _environ({}) == {}
    assert _environ() is os.environ


def test_update_notice_reads_the_injected_env(monkeypatch):
    from quodeq import cli

    monkeypatch.setenv("QUODEQ_NO_UPDATE_NOTIFIER", "1")
    calls: list[int] = []
    monkeypatch.setattr(cli, "check_async", lambda: calls.append(1))
    monkeypatch.setattr(cli, "get_status", lambda: {"disclosed": True})

    out = io.StringIO()
    out.isatty = lambda: True  # type: ignore[method-assign]

    # Opted out via the injected mapping: nothing runs.
    cli.maybe_emit_cli_notice(out, env={"QUODEQ_NO_UPDATE_NOTIFIER": "1"})
    assert calls == []

    # Empty mapping: the process opt-out must NOT be consulted.
    cli.maybe_emit_cli_notice(out, env={})
    assert calls == [1]


def test_update_notice_treats_injected_ci_as_non_interactive(monkeypatch):
    from quodeq import cli

    calls: list[int] = []
    monkeypatch.setattr(cli, "check_async", lambda: calls.append(1))
    monkeypatch.setattr(cli, "get_status", lambda: {"disclosed": True})
    out = io.StringIO()
    out.isatty = lambda: True  # type: ignore[method-assign]

    cli.maybe_emit_cli_notice(out, env={"CI": "true"})
    assert calls == []


def _limits_args() -> argparse.Namespace:
    return argparse.Namespace(
        max_turns=None, max_duration=None, n_subagents=None, no_verify=False,
        pool_budget=None, clean_scan=False, diff_from=None, dry_run=False,
    )


def test_resolve_limits_reads_caps_from_the_injected_env(monkeypatch):
    from quodeq._cli_run_config import _resolve_limits

    monkeypatch.setenv("QUODEQ_MAX_TURNS", "77")
    monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", "77")

    injected = _resolve_limits(_limits_args(), {
        "QUODEQ_MAX_TURNS": "12", "QUODEQ_MAX_API_FILE_SIZE": "999",
    })
    assert injected.max_turns == 12
    assert injected.dispatch_policy.file_size_cap == 999

    # An empty mapping means "no variables set" for the dispatch policy the
    # boundary builds. (``max_turns`` still goes through ``_cli_env._env_int``,
    # whose own `or os.environ` fallback is a separate task's site.)
    empty = _resolve_limits(_limits_args(), {})
    assert empty.dispatch_policy.file_size_cap == 15000


def test_run_config_locals_read_consolidation_from_the_injected_env(monkeypatch):
    from quodeq._cli_evaluation import _resolve_run_config_locals
    from quodeq._cli_resolution import ResolvedInputs

    monkeypatch.setenv("QUODEQ_NO_CONSOLIDATE", "1")
    args = argparse.Namespace(no_consolidated=False, diff_from=None, _diff_files=None)
    inputs = ResolvedInputs(
        src=".", language="python", manifest=None, dims_data=None, single_file=None,
    )

    off = _resolve_run_config_locals(args, inputs, {"QUODEQ_NO_CONSOLIDATE": "1"})
    assert off.consolidated is False
    # Empty mapping: the exported opt-out must not be consulted.
    on = _resolve_run_config_locals(args, inputs, {})
    assert on.consolidated is True


def test_run_config_locals_read_the_subagent_model_from_the_injected_env():
    from quodeq._cli_evaluation import _resolve_run_config_locals
    from quodeq._cli_resolution import ResolvedInputs

    args = argparse.Namespace(no_consolidated=False, diff_from=None, _diff_files=None)
    inputs = ResolvedInputs(
        src=".", language="python", manifest=None, dims_data=None, single_file=None,
    )

    injected = _resolve_run_config_locals(args, inputs, {"SUBAGENT_MODEL": "m-1"})
    assert injected.subagent_model == "m-1"
