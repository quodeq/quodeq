"""Tests for branch and scope_path params in evaluation dispatch."""

from __future__ import annotations

from pathlib import Path

from quodeq.services.base import EvaluationOptions
from quodeq.services.evaluation_mixin import _build_evaluate_cmd


def test_build_cmd_includes_branch(tmp_path: Path) -> None:
    """Branch option should appear in the CLI command."""
    options = EvaluationOptions(branch="feature/auth")
    cmd = _build_evaluate_cmd(str(tmp_path), options, str(tmp_path / "reports"))
    assert "--branch" in cmd
    idx = cmd.index("--branch")
    assert cmd[idx + 1] == "feature/auth"


def test_build_cmd_includes_scope_path(tmp_path: Path) -> None:
    """Scope path option should appear in the CLI command."""
    options = EvaluationOptions(scope_path="src/backend")
    cmd = _build_evaluate_cmd(str(tmp_path), options, str(tmp_path / "reports"))
    assert "--scope" in cmd
    idx = cmd.index("--scope")
    assert cmd[idx + 1] == "src/backend"


def test_build_cmd_omits_branch_when_none(tmp_path: Path) -> None:
    """No branch flag when branch is None."""
    options = EvaluationOptions()
    cmd = _build_evaluate_cmd(str(tmp_path), options, str(tmp_path / "reports"))
    assert "--branch" not in cmd
    assert "--scope" not in cmd
