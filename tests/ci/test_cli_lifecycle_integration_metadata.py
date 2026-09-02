"""Integration tests — provider/model metadata and deadline extension wiring.

Split from test_cli_lifecycle_integration.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

from quodeq.data.fs.run_status_store import read_status


def test_pipeline_records_provider_and_model_from_env(tmp_path: Path, monkeypatch) -> None:
    """status.json records the AI_PROVIDER/AI_MODEL the CLI ran with."""
    import quodeq._cli_evaluation as cli

    monkeypatch.setenv("AI_PROVIDER", "test-provider")
    monkeypatch.setenv("AI_MODEL", "test-model")

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        args = argparse.Namespace(repo="local")
        inputs = cli.ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data=None)
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None, "status.json must be written"
    assert status["ai_provider"] == "test-provider"
    assert status["ai_model"] == "test-model"


def test_pipeline_records_ai_cmd_as_provider(tmp_path: Path, monkeypatch) -> None:
    """status.json records AI_CMD as ai_provider when AI_CMD is set (not AI_PROVIDER).

    Locks in get_ai_cmd() semantics: the pipeline selects its provider via
    AI_CMD → AI_PROVIDER → default; the external path must record the same
    value as the internal path's options.ai_cmd.
    """
    import quodeq._cli_evaluation as cli

    monkeypatch.setenv("AI_CMD", "llamacpp")
    monkeypatch.setenv("AI_MODEL", "qwen3.6-27b")
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        args = argparse.Namespace(repo="local")
        inputs = cli.ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data=None)
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None, "status.json must be written"
    assert status["ai_provider"] == "llamacpp"
    assert status["ai_model"] == "qwen3.6-27b"


def test_pool_deadline_extension_reaches_status_json(tmp_path: Path) -> None:
    """The deadline-extension callback is wired to the lifecycle before the
    pipeline runs: invoking it (as the pool auto-scale does) must land the
    new deadline in status.json, where the dashboard countdown and the
    post-#956 exit-reason labeling read it."""
    import quodeq._cli_evaluation as cli
    from quodeq.analysis._types import RunConfig

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    config = RunConfig(src=tmp_path, language="python")
    extended_iso = "2026-08-01T12:00:00+00:00"

    def _fake_pipeline(*_a, **_k):
        cb = config.options.on_deadline_extended
        assert cb is not None, "extension callback must be wired before the pipeline runs"
        cb(extended_iso)
        return 0

    with patch.object(cli, "_execute_pipeline", side_effect=_fake_pipeline), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config", return_value=config), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        args = argparse.Namespace(repo="local", pool_budget=60)
        inputs = cli.ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data=None)
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    status = read_status(evaluation_dir.parent)
    assert status is not None
    assert status["deadline_at"] == extended_iso
