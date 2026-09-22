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


def test_resolve_limits_reads_every_cap_from_the_injected_env(monkeypatch):
    from quodeq._cli_run_config import _resolve_limits

    # Every cap this phase reads, exported in the process environment.
    exported = {
        "QUODEQ_MAX_TURNS": "77", "QUODEQ_MAX_DURATION": "77",
        "QUODEQ_TIME_LIMIT": "77", "QUODEQ_NO_VERIFY": "1",
        "QUODEQ_MAX_API_FILE_SIZE": "77", "AI_CMD": "ollama",
    }
    for var, value in exported.items():
        monkeypatch.setenv(var, value)

    injected = _resolve_limits(_limits_args(), {
        "QUODEQ_MAX_TURNS": "12",
        "QUODEQ_MAX_DURATION": "34",
        "QUODEQ_TIME_LIMIT": "56",
        "QUODEQ_NO_VERIFY": "1",
        "QUODEQ_MAX_API_FILE_SIZE": "999",
        "AI_CMD": "codex",
    })
    assert injected.max_turns == 12
    assert injected.max_duration == 34
    assert injected.time_limit == 56
    assert injected.verify_findings is False
    assert injected.dispatch_policy.file_size_cap == 999
    assert injected.dispatch_policy.ai_cmd == "codex"

    # An empty mapping means "no variables set": every cap falls back to its
    # packaged default even though all six are exported in the process.
    empty = _resolve_limits(_limits_args(), {})
    assert empty.max_turns is None
    assert empty.max_duration is None
    assert empty.time_limit is None
    assert empty.verify_findings is True
    assert empty.dispatch_policy.file_size_cap == 15000
    assert empty.dispatch_policy.ai_cmd == "claude"  # the packaged default


def test_run_config_locals_read_consolidation_from_the_injected_env(monkeypatch):
    from quodeq.cli_evaluation import _resolve_run_config_locals
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


def test_run_config_locals_read_the_subagent_model_from_the_injected_env(monkeypatch):
    from quodeq.cli_evaluation import _resolve_run_config_locals
    from quodeq._cli_resolution import ResolvedInputs

    monkeypatch.setenv("SUBAGENT_MODEL", "from-process")
    args = argparse.Namespace(no_consolidated=False, diff_from=None, _diff_files=None)
    inputs = ResolvedInputs(
        src=".", language="python", manifest=None, dims_data=None, single_file=None,
    )

    injected = _resolve_run_config_locals(args, inputs, {"SUBAGENT_MODEL": "m-1"})
    assert injected.subagent_model == "m-1"
    # Empty mapping: the exported override must not be consulted.
    assert _resolve_run_config_locals(args, inputs, {}).subagent_model is None
