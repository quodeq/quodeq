"""assistant, cli, and lifecycle best-effort handlers log at debug."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.assistant.mcp import mcp_config
from quodeq.assistant.tools import _read_tools_scope
from quodeq.llm_bridge import _ollama


def test_unregister_locked_logs_when_cli_is_missing(monkeypatch) -> None:
    def _missing(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file", "claude")

    monkeypatch.setattr(mcp_config.subprocess, "run", _missing)
    with patch.object(mcp_config._logger, "debug") as debug:
        mcp_config._unregister_locked("claude")
    assert debug.called
    # The log call is lazy %-style (cmd, exc as separate args, not inlined
    # into the message), so render it before checking for "claude".
    message = debug.call_args.args[0] % debug.call_args.args[1:]
    assert "unregister via claude failed" in message


def test_detect_memory_logs_and_returns_zero(monkeypatch) -> None:
    def _missing(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file", "sysctl")

    # detect_memory only probes on Darwin/Linux; force Linux so the (mocked)
    # nvidia-smi probe runs on every platform, including Windows CI.
    monkeypatch.setattr(_ollama.platform, "system", lambda: "Linux")
    monkeypatch.setattr(_ollama.subprocess, "check_output", _missing)
    with patch.object(_ollama._log, "debug") as debug:
        assert _ollama.detect_memory() == 0
    assert debug.called
    assert "memory detection failed" in debug.call_args.args[0]


def test_worktree_remove_logs_when_branch_delete_fails(monkeypatch, tmp_path) -> None:
    # Import via worktree.py, not _worktree_manager directly: worktree.py's
    # module-level re-export makes it the module that must load first (see
    # its own comment at the re-export site), else a direct
    # `from quodeq.assistant import _worktree_manager` triggers a circular
    # partially-initialized-module ImportError.
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    from quodeq.assistant import _worktree_manager

    manager = WorktreeManager(
        repo_root=tmp_path / "repo",
        path=tmp_path / "wt",  # never created -> exists() is False
        branch="quodeq/fix-test1234",
    )

    def fake_run(argv, **kwargs):
        if "branch" in argv and "-D" in argv:
            raise WorktreeError("boom")
        return ""

    monkeypatch.setattr(_worktree_manager, "run_git", fake_run)
    with patch.object(_worktree_manager._logger, "debug") as debug:
        manager.remove(delete_branch=True)
    assert debug.called
    assert manager.branch in debug.call_args.args


def test_accumulated_finding_keys_logs_and_never_calls_add(monkeypatch) -> None:
    def _raise(*_args, **_kwargs):
        raise OSError(5, "boom")

    monkeypatch.setattr(_read_tools_scope, "accumulated_dims", _raise)
    added: list = []
    with patch.object(_read_tools_scope._logger, "debug") as debug:
        _read_tools_scope._accumulated_finding_keys(None, added.append)
    assert added == []
    assert debug.called
    assert "accumulated findings unavailable" in debug.call_args.args[0]


def test_scored_run_dims_logs_and_returns_none_on_failure(monkeypatch, tmp_path) -> None:
    from quodeq.assistant.tools import ToolContext

    run_dir = tmp_path / "reports" / "proj" / "run-1"
    run_dir.mkdir(parents=True)
    ctx = ToolContext(
        repository=None, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )
    monkeypatch.setattr(_read_tools_scope, "dismissed_keys", lambda _p: {("r", "f", 1)})
    monkeypatch.setattr(_read_tools_scope, "deleted_keys", lambda _p: set())

    def _raise(*_args, **_kwargs):
        raise ValueError("bad run id")

    monkeypatch.setattr(_read_tools_scope, "scored_run_dimensions", _raise)

    with patch.object(_read_tools_scope._logger, "warning") as warning:
        result = _read_tools_scope.scored_run_dims(ctx)

    assert result is None
    assert warning.called
    assert "scored_run_dims failed" in warning.call_args.args[0]


def _sql_keys_ctx(tmp_path, list_keys_fn):
    from quodeq.assistant.tools import ToolContext

    run_dir = tmp_path / "reports" / "proj" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.db").write_bytes(b"x")

    class _Repo:
        def list_keys(self):
            return list_keys_fn()

    return ToolContext(
        repository=None, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        findings_repo_factory=lambda _run_dir: _Repo(),
    )


def test_sql_finding_keys_logs_and_returns_false_on_a_db_read_failure(monkeypatch, tmp_path) -> None:
    import sqlite3

    def _raise():
        raise sqlite3.OperationalError("database disk image is malformed")

    ctx = _sql_keys_ctx(tmp_path, _raise)
    keys: set = set()

    with patch.object(_read_tools_scope._logger, "warning") as warning:
        complete = _read_tools_scope._sql_finding_keys(ctx, keys)

    assert complete is False
    assert keys == set()
    assert warning.called
    assert "evaluation.db unreadable" in warning.call_args.args[0]


def test_sql_finding_keys_propagates_an_error_outside_the_narrowed_tuple(tmp_path) -> None:
    """A RuntimeError from list_keys is not sqlite3.Error/OSError/ValueError,
    so it is a real bug, not a corrupt-db read failure, and now escapes
    instead of being swallowed as a warning."""
    def _raise():
        raise RuntimeError("unexpected bug")

    ctx = _sql_keys_ctx(tmp_path, _raise)
    keys: set = set()

    with pytest.raises(RuntimeError):
        _read_tools_scope._sql_finding_keys(ctx, keys)


def test_cli_hook_logs_and_swallows_when_dup2_fails(monkeypatch) -> None:
    from quodeq import cli

    previous_hook = sys.excepthook
    try:
        cli._install_broken_pipe_guard()
        hook = sys.excepthook

        def _raise(*_args):
            raise OSError(9, "Bad file descriptor")

        monkeypatch.setattr(os, "dup2", _raise)
        try:
            with patch.object(cli._logger, "debug") as debug:
                result = hook(BrokenPipeError, BrokenPipeError(), None)
        finally:
            # Restore the real os.dup2 now, before pytest's own fd-capture
            # teardown calls it to restore stdout/stderr.
            monkeypatch.undo()
        assert result is None
        assert debug.called
        assert "could not redirect stdio" in debug.call_args.args[0]
    finally:
        sys.excepthook = previous_hook


def test_cleanup_run_artifacts_logs_when_pid_unlink_fails(monkeypatch, tmp_path) -> None:
    import quodeq._cli_lifecycle as lifecycle
    from quodeq.cli_evaluation import _lifecycle_hooks
    from quodeq.cli import ResolvedInputs

    pid_file = tmp_path / ".pid"
    args = argparse.Namespace(repo="/tmp/repo")
    inputs = ResolvedInputs(src=Path("/tmp/repo"), language="python", manifest=None, dims_data={})

    def _raise(*_args, **_kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(Path, "unlink", _raise)
    with patch.object(lifecycle._logger, "debug") as debug:
        lifecycle._cleanup_run_artifacts(pid_file, args, inputs, _lifecycle_hooks())
    assert debug.called
    assert "pid file cleanup failed" in debug.call_args.args[0]


def test_run_pipeline_with_cleanup_logs_when_pid_write_fails(monkeypatch, tmp_path) -> None:
    import quodeq._cli_lifecycle as lifecycle
    from quodeq.cli_evaluation import run_pipeline_with_cleanup
    from quodeq.cli import ResolvedInputs

    class _Sentinel(Exception):
        pass

    run_dir = tmp_path / "run"
    evidence_dir = run_dir / "evidence"
    evaluation_dir = run_dir / "evaluation"
    args = argparse.Namespace()
    inputs = ResolvedInputs(src=Path("/tmp/repo"), language="python", manifest=None, dims_data={})

    def _raise_write(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    def _raise_sentinel(*_args, **_kwargs):
        raise _Sentinel()

    monkeypatch.setattr(Path, "write_text", _raise_write)
    monkeypatch.setattr("quodeq.cli_evaluation.build_run_config", _raise_sentinel)

    with patch.object(lifecycle._logger, "debug") as debug:
        with pytest.raises(_Sentinel):
            run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))
    assert debug.called
    assert "pid file write failed" in debug.call_args.args[0]
