"""Tests for CLI command dispatch — build_manifest, execute_pipeline, save_manifest, build_run_config, run_evaluate, main()."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _build_manifest tests
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_no_prescan_returns_none(self):
        from quodeq.cli import _build_manifest
        args = argparse.Namespace(no_prescan=True)
        result = _build_manifest(args, Path("/tmp"), MagicMock())
        assert result is None

    def test_detection_file_missing_returns_none(self):
        from quodeq.cli import _build_manifest
        args = argparse.Namespace(no_prescan=False)
        paths = MagicMock()
        paths.detection_file.exists.return_value = False
        result = _build_manifest(args, Path("/tmp"), paths)
        assert result is None


# ---------------------------------------------------------------------------
# _execute_pipeline tests
# ---------------------------------------------------------------------------

class TestExecutePipeline:
    @patch("quodeq._cli_evaluation.run")
    @patch("quodeq._cli_evaluation.write_text")
    def test_evidence_only_success(self, mock_write, mock_run, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=True, mode="numerical")
        mock_evidence = MagicMock()
        mock_evidence.to_evidence_dict.return_value = {"data": "test"}
        mock_run.return_value = mock_evidence
        config = MagicMock()
        config.language = "python"
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0
        mock_run.assert_called_once_with(config)

    @patch("quodeq._cli_evaluation.run")
    @patch("quodeq._cli_evaluation.write_text", side_effect=OSError("disk full"))
    def test_evidence_only_write_failure(self, mock_write, mock_run, tmp_path, capsys):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=True, mode="numerical")
        mock_evidence = MagicMock()
        mock_evidence.to_evidence_dict.return_value = {}
        mock_run.return_value = mock_evidence
        config = MagicMock()
        config.language = "python"
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 1
        assert "Failed to write" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation.run_full")
    def test_full_pipeline_success(self, mock_run_full, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.return_value = {"security": 8.5, "reliability": 7.0}
        config = MagicMock()
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0

    @patch("quodeq._cli_evaluation.run_full")
    def test_pipeline_analysis_error(self, mock_run_full, tmp_path, capsys):
        # AnalysisError propagates from _execute_pipeline so that the outer
        # RunLifecycleContext can write state=failed.  The caller
        # (_run_pipeline_with_cleanup) is responsible for mapping it to exit 1.
        import pytest
        from quodeq.cli import _execute_pipeline
        from quodeq.analysis.subprocess import AnalysisError
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.side_effect = AnalysisError("AI failed")
        config = MagicMock()
        config.options.skip_scoring = False
        with pytest.raises(AnalysisError, match="AI failed"):
            _execute_pipeline(args, config, evidence_dir, evaluation_dir)


# ---------------------------------------------------------------------------
# _save_manifest tests
# ---------------------------------------------------------------------------

class TestSaveManifest:
    @patch("quodeq._cli_evaluation.write_text")
    def test_saves_when_manifest_exists(self, mock_write, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        manifest.to_dict.return_value = {"targets": []}
        _save_manifest(manifest, tmp_path)
        mock_write.assert_called_once()

    def test_none_manifest_no_op(self, tmp_path):
        from quodeq.cli import _save_manifest
        _save_manifest(None, tmp_path)  # should not raise

    @patch("quodeq._cli_evaluation.write_text", side_effect=OSError("fail"))
    def test_os_error_silenced(self, mock_write, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        manifest.to_dict.return_value = {}
        _save_manifest(manifest, tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# _build_run_config tests
# ---------------------------------------------------------------------------

class TestBuildRunConfig:
    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
    def test_basic_config(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
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
        from quodeq.cli import _build_run_config, ResolvedInputs
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
        from quodeq.cli import _build_run_config, ResolvedInputs
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False, _single_file=True,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.options.consolidated is False

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_no_consolidate(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
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
        from quodeq.cli import _build_run_config, ResolvedInputs
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


# ---------------------------------------------------------------------------
# run_evaluate tests
# ---------------------------------------------------------------------------

class TestRunEvaluate:
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs", side_effect=RuntimeError("no claude"))
    def test_prereqs_failure(self, mock_prereqs, capsys):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1
        assert "no claude" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation._resolve_evaluation_inputs", return_value=None)
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs")
    def test_resolve_inputs_none(self, mock_prereqs, mock_resolve):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1

    @patch("quodeq._cli_evaluation._run_pipeline_with_cleanup", return_value=0)
    @patch("quodeq._cli_evaluation._setup_run_dirs")
    @patch("quodeq._cli_evaluation._resolve_evaluation_inputs")
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs")
    def test_successful_evaluate(self, mock_prereqs, mock_resolve, mock_dirs, mock_pipeline):
        from quodeq.cli import run_evaluate, ResolvedInputs
        mock_resolve.return_value = ResolvedInputs(
            src=Path("/tmp/repo"), language="python", manifest=None, dims_data={}
        )
        mock_dirs.return_value = (Path("/tmp/out"), Path("/tmp/ev"), Path("/tmp/eval"))
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 0
        mock_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# --clean-scan / --incremental flag tests
# ---------------------------------------------------------------------------

@patch("quodeq._cli_evaluation.default_paths")
@patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
def test_clean_scan_flag_parsed_and_inverts_strategy(mock_model, mock_paths, tmp_path):
    """--clean-scan disables the internal incremental strategy."""
    from quodeq._cli_evaluation import _build_run_config, ResolvedInputs
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
    from quodeq._cli_evaluation import _build_run_config, ResolvedInputs
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
    from quodeq._cli_evaluation import _build_run_config, ResolvedInputs, run_evaluate
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

