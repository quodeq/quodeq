"""Tests for CLI run-config building — _build_run_config and the --clean-scan / --incremental flags."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch


class TestBuildRunConfig:
    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
    def test_basic_config(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, _build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = True
        mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="python", manifest=None, dims_data={}
        )
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.language == "python"
        assert config.options.verify_findings is True

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value=None)
    def test_subagent_model_fallback(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, _build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions="security,reliability", no_consolidated=False,
            no_verify=True, max_turns=10, max_duration=300,
            n_subagents=3, pool_budget=120, clean_scan=False, legacy_incremental=False,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="java", manifest=None, dims_data={}
        )
        env = {"SUBAGENT_MODEL": "ollama/llama3"}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model == "ollama/llama3"
        assert config.options.dimensions == ["security", "reliability"]
        assert config.options.max_turns == 10
        assert config.options.max_duration == 300
        assert config.options.time_limit == 120
        assert config.options.incremental is True  # clean_scan=False → incremental=True (internal strategy)
        assert config.options.verify_findings is False
        assert config.standards_dir is None

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
    def test_single_file_disables_consolidated(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, _build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="python", manifest=None, dims_data={}, single_file=True,
        )
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.options.consolidated is False

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_no_consolidate(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, _build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={"QUODEQ_NO_CONSOLIDATE": "1"})
        assert config.options.consolidated is False

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_overrides_for_turns_and_duration(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, _build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        env = {"QUODEQ_MAX_TURNS": "50", "QUODEQ_MAX_DURATION": "900", "QUODEQ_POOL_BUDGET": "300"}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.max_turns == 50
        assert config.options.max_duration == 900
        # Legacy QUODEQ_POOL_BUDGET still routes into time_limit via the env-var fallback.
        assert config.options.time_limit == 300

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_time_limit_zero_is_unlimited(self, mock_model, mock_paths, tmp_path):
        # Contract pin: the dashboard propagates unlimited as
        # QUODEQ_TIME_LIMIT=0. It must resolve to 0 (not None), otherwise
        # the pool substitutes its 600s default and unlimited runs die at
        # 10 minutes.
        from quodeq.cli import ResolvedInputs, _build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={"QUODEQ_TIME_LIMIT": "0"})
        assert config.options.time_limit == 0


@patch("quodeq._cli_evaluation.default_paths")
@patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
def test_clean_scan_flag_parsed_and_inverts_strategy(mock_model, mock_paths, tmp_path):
    """--clean-scan disables the internal incremental strategy."""
    from quodeq._cli_evaluation import ResolvedInputs, _build_run_config
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
    config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path)
    assert config.options.incremental is False, "--clean-scan must set AnalysisOptions.incremental=False"


@patch("quodeq._cli_evaluation.default_paths")
@patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
def test_no_flag_means_incremental_default(mock_model, mock_paths, tmp_path):
    """Without --clean-scan, the internal strategy is incremental (the new default)."""
    from quodeq._cli_evaluation import ResolvedInputs, _build_run_config
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
    config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path)
    assert config.options.incremental is True


@patch("quodeq._cli_evaluation.default_paths")
@patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
def test_legacy_incremental_flag_warns_but_works(mock_model, mock_paths, tmp_path, capsys):
    """--incremental is accepted as a no-op deprecated alias: it warns AND yields incremental=True."""
    from quodeq._cli_evaluation import ResolvedInputs, _build_run_config, run_evaluate
    from quodeq.cli_parser import build_parser

    mock_paths_obj = MagicMock()
    mock_paths_obj.standards_dir.exists.return_value = False
    mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
    mock_paths.return_value = mock_paths_obj

    (tmp_path / "app.py").write_text("")
    parser = build_parser()
    args = parser.parse_args([
        "evaluate", str(tmp_path), "-d", "security", "--incremental",
    ])

    # Confirm argparse wiring: --incremental maps to legacy_incremental, not clean_scan.
    assert args.legacy_incremental is True
    assert args.clean_scan is False

    # "works" half: legacy_incremental is a no-op; incremental stays True (the default).
    # A future regression that translates legacy_incremental=True to incremental=False
    # must fail here.
    inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
    config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path)
    assert config.options.incremental is True, (
        "--incremental (legacy) must not change incremental=True default; "
        "a boolean-translation regression would break this."
    )

    # "warns" half: run_evaluate emits the deprecation warning to stderr via the
    # quodeq logger (propagate=False, StderrHandler), so capsys captures it.
    with patch("quodeq._cli_evaluation._resolve_evaluation_inputs", return_value=None):
        with patch("quodeq._cli_evaluation.check_evaluate_prereqs"):
            run_evaluate(args)
    captured = capsys.readouterr()
    assert "deprecated" in captured.err.lower(), (
        "run_evaluate must emit a deprecation warning when --incremental is passed"
    )


def test_diff_from_forces_clean_scan_internally(tmp_path):
    """--diff-from is evidence-only, so internally it forces incremental=False."""
    from quodeq._cli_evaluation import _build_run_config
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
    # Simulate what run_evaluate does before calling _build_run_config
    args._diff_files = {"changed.py"}

    inputs = ResolvedInputs(
        src=repo,
        language="python",
        manifest=SourceManifest(),
        dims_data={"applies": []},
    )
    config = _build_run_config(args, inputs=inputs, evidence_dir=repo / "evi")
    assert config.options.incremental is False

