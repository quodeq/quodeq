"""Tests for CLI run-config building — the --clean-scan / --incremental / --diff-from flags.

Split from test_cli_run_config.py (which keeps TestBuildRunConfig) to stay
under the test-file size gate.
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest


@patch("quodeq.cli_evaluation.default_paths")
@patch("quodeq.cli_evaluation.get_ai_model", return_value="claude-3")
def test_clean_scan_flag_parsed_and_inverts_strategy(mock_model, mock_paths, tmp_path):
    """--clean-scan disables the internal incremental strategy."""
    from quodeq.cli_evaluation import ResolvedInputs, build_run_config
    from quodeq.cli_parser import build_parser

    mock_paths_obj = MagicMock()
    mock_paths_obj.standards_dir.exists.return_value = False
    mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
    mock_paths.return_value = mock_paths_obj

    (tmp_path / "app.py").write_text("")
    parser = build_parser()
    args = parser.parse_args([
        "evaluate", str(tmp_path), "-d", "security", "--clean-scan",
    ])
    inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
    config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path)
    assert config.options.incremental is False, "--clean-scan must set AnalysisOptions.incremental=False"


@patch("quodeq.cli_evaluation.default_paths")
@patch("quodeq.cli_evaluation.get_ai_model", return_value="claude-3")
def test_no_flag_means_incremental_default(mock_model, mock_paths, tmp_path):
    """Without --clean-scan, the internal strategy is incremental (the new default)."""
    from quodeq.cli_evaluation import ResolvedInputs, build_run_config
    from quodeq.cli_parser import build_parser

    mock_paths_obj = MagicMock()
    mock_paths_obj.standards_dir.exists.return_value = False
    mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
    mock_paths.return_value = mock_paths_obj

    (tmp_path / "app.py").write_text("")
    parser = build_parser()
    args = parser.parse_args([
        "evaluate", str(tmp_path), "-d", "security",
    ])
    inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
    config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path)
    assert config.options.incremental is True


@pytest.fixture()
def _legacy_incremental_args(tmp_path):
    """Parse ``evaluate --incremental`` once; each test below checks one
    consequence of the legacy flag (argparse wiring, config building, or
    the deprecation warning)."""
    from quodeq.cli_parser import build_parser

    (tmp_path / "app.py").write_text("")
    parser = build_parser()
    return parser.parse_args([
        "evaluate", str(tmp_path), "-d", "security", "--incremental",
    ])


def test_legacy_incremental_flag_maps_to_legacy_incremental_not_clean_scan(_legacy_incremental_args):
    """Confirm argparse wiring: --incremental maps to legacy_incremental, not clean_scan."""
    assert _legacy_incremental_args.legacy_incremental is True
    assert _legacy_incremental_args.clean_scan is False


@patch("quodeq.cli_evaluation.default_paths")
@patch("quodeq.cli_evaluation.get_ai_model", return_value="claude-3")
def test_legacy_incremental_flag_still_yields_incremental_true(
    mock_model, mock_paths, tmp_path, _legacy_incremental_args,
):
    """legacy_incremental is a no-op; incremental stays True (the default). A
    future regression that translates legacy_incremental=True to
    incremental=False must fail here."""
    from quodeq.cli_evaluation import ResolvedInputs, build_run_config

    mock_paths_obj = MagicMock()
    mock_paths_obj.standards_dir.exists.return_value = False
    mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
    mock_paths.return_value = mock_paths_obj

    inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
    config = build_run_config(_legacy_incremental_args, inputs=inputs, evidence_dir=tmp_path)
    assert config.options.incremental is True, (
        "--incremental (legacy) must not change incremental=True default; "
        "a boolean-translation regression would break this."
    )


@patch("quodeq.cli_evaluation.default_paths")
@patch("quodeq.cli_evaluation.get_ai_model", return_value="claude-3")
def test_legacy_incremental_flag_warns_on_run(mock_model, mock_paths, tmp_path, capsys, _legacy_incremental_args):
    """run_evaluate emits the deprecation warning to stderr via the quodeq
    logger (propagate=False, StderrHandler), so capsys captures it."""
    from quodeq.cli_evaluation import run_evaluate

    mock_paths_obj = MagicMock()
    mock_paths_obj.standards_dir.exists.return_value = False
    mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
    mock_paths.return_value = mock_paths_obj

    with patch("quodeq.cli_evaluation._resolve_evaluation_inputs", return_value=None):
        with patch("quodeq.cli_evaluation.check_evaluate_prereqs"):
            run_evaluate(_legacy_incremental_args)
    captured = capsys.readouterr()
    assert "deprecated" in captured.err.lower(), (
        "run_evaluate must emit a deprecation warning when --incremental is passed"
    )


def test_diff_from_forces_clean_scan_internally(tmp_path):
    """--diff-from is evidence-only, so internally it forces incremental=False."""
    from quodeq.cli_evaluation import build_run_config
    from quodeq._cli_resolution import ResolvedInputs
    from quodeq.analysis.manifest_models import SourceManifest

    repo = tmp_path / "repo"
    repo.mkdir()

    import subprocess
    def run_git(cmd):
        subprocess.run(cmd, cwd=str(repo), check=True, capture_output=True)

    run_git(["git", "init", "-q", "-b", "main"])
    run_git(["git", "config", "user.email", "t@t"])
    run_git(["git", "config", "user.name", "t"])
    (repo / "base.py").write_text("x = 1\n")
    run_git(["git", "add", "."])
    run_git(["git", "commit", "-q", "-m", "base"])
    run_git(["git", "checkout", "-q", "-b", "feature"])
    (repo / "changed.py").write_text("y = 2\n")
    run_git(["git", "add", "."])
    run_git(["git", "commit", "-q", "-m", "add changed"])

    args = argparse.Namespace(
        repo=str(repo),
        output=str(repo / "out"),
        language=None,
        dimensions="security",
        max_turns=None,
        max_duration=None,
        n_subagents=1,
        no_verify=False,
        pool_budget=None,
        no_consolidated=False,
        clean_scan=False,
        legacy_incremental=False,
        diff_from="main",
        dry_run=False,
        mode="numerical",
        evidence_only=False,
    )
    # Simulate what run_evaluate does before calling build_run_config
    args._diff_files = {"changed.py"}

    inputs = ResolvedInputs(
        src=repo,
        language="python",
        manifest=SourceManifest(),
        dims_data={"applies": []},
    )
    config = build_run_config(args, inputs=inputs, evidence_dir=repo / "evi")
    assert config.options.incremental is False
