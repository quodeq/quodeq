"""Test that --diff-from populates RunConfig options correctly."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from quodeq._cli_evaluation import _build_run_config
from quodeq._cli_resolution import ResolvedInputs
from quodeq.analysis.manifest_models import SourceManifest


def _make_repo_with_diff(tmp_path: Path) -> Path:
    """One-file repo with main + feature branch that adds changed.py."""
    repo = tmp_path / "repo"
    repo.mkdir()
    def run(cmd: list[str]) -> None:
        subprocess.run(cmd, cwd=str(repo), check=True, capture_output=True)
    run(["git", "init", "-q", "-b", "main"])
    run(["git", "config", "user.email", "t@t"])
    run(["git", "config", "user.name", "t"])
    (repo / "base.py").write_text("x = 1\n")
    run(["git", "add", "."])
    run(["git", "commit", "-q", "-m", "base"])
    run(["git", "checkout", "-q", "-b", "feature"])
    (repo / "changed.py").write_text("y = 2\n")
    run(["git", "add", "."])
    run(["git", "commit", "-q", "-m", "add changed"])
    return repo


def _args(repo: Path, **overrides) -> argparse.Namespace:
    defaults = dict(
        repo=str(repo),
        output=str(repo / "out"),
        language=None,
        dimensions=None,
        max_turns=None,
        max_duration=None,
        n_subagents=1,
        no_verify=False,
        pool_budget=None,
        no_consolidated=False,
        incremental=False,
        diff_from=None,
        dry_run=False,
        mode="numerical",
        evidence_only=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _inputs(repo: Path) -> ResolvedInputs:
    # SourceManifest's modern API uses targets; an empty manifest is fine
    # because _build_run_config only passes it through to RunConfig.
    manifest = SourceManifest()
    return ResolvedInputs(
        src=repo,
        language="python",
        manifest=manifest,
        dims_data={"applies": []},
    )


def test_diff_from_populates_file_filter_and_skip_scoring(tmp_path: Path) -> None:
    repo = _make_repo_with_diff(tmp_path)
    args = _args(repo, diff_from="main")
    config = _build_run_config(args, inputs=_inputs(repo), evidence_dir=repo / "evi")
    assert config.options.diff_from == "main"
    assert config.options.skip_scoring is True
    assert config.options.incremental_file_filter == {"changed.py"}


def test_no_diff_from_leaves_file_filter_unset(tmp_path: Path) -> None:
    repo = _make_repo_with_diff(tmp_path)
    args = _args(repo, diff_from=None)
    config = _build_run_config(args, inputs=_inputs(repo), evidence_dir=repo / "evi")
    assert config.options.diff_from is None
    assert config.options.skip_scoring is False
    assert config.options.incremental_file_filter is None
