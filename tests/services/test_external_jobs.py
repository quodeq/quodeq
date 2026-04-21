"""Tests for the cancel path of external (CLI-started) evaluations."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# PID resolution
# ---------------------------------------------------------------------------

def test_resolve_external_pid_returns_none_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert resolve_external_pid("proj", "run", tmp_path) is None


def test_resolve_external_pid_returns_pid_when_alive(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text(str(os.getpid()))
    assert resolve_external_pid("proj", "run", tmp_path) == os.getpid()


def test_resolve_external_pid_returns_none_when_process_dead(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    # Use a very high PID that's almost certainly not in use
    (run_dir / ".pid").write_text("999999")
    assert resolve_external_pid("proj", "run", tmp_path) is None


def test_resolve_external_pid_returns_none_for_corrupt_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text("not-a-number")
    assert resolve_external_pid("proj", "run", tmp_path) is None


# ---------------------------------------------------------------------------
# cancel_external_run
# ---------------------------------------------------------------------------

def test_cancel_external_run_returns_false_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import cancel_external_run

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert cancel_external_run("proj", "run", tmp_path) is False
