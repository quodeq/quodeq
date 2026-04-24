"""_execute_pipeline must skip scoring when options.skip_scoring is set."""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

from quodeq._cli_evaluation import _execute_pipeline
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.manifest_models import SourceManifest
from quodeq.core.evidence.model import Evidence


def _args(tmp: Path) -> argparse.Namespace:
    return argparse.Namespace(
        evidence_only=False, mode="numerical", repo=str(tmp),
    )


def _config(skip_scoring: bool) -> RunConfig:
    manifest = SourceManifest()
    return RunConfig(
        src=Path("/tmp"), language="python", manifest=manifest,
        dimensions_data={"applies": [{"id": "security"}]},
        options=AnalysisOptions(skip_scoring=skip_scoring),
    )


def _fake_evidence() -> Evidence:
    return Evidence(
        repository="/tmp", language="python", date="x",
        source_file_count=1, files_read=1, coverage_pct=100.0,
    )


def test_skip_scoring_calls_run_not_run_full(tmp_path: Path) -> None:
    """PR diff mode: run() is called (evidence pipeline), run_full is NOT."""
    args = _args(tmp_path)
    config = _config(skip_scoring=True)
    with patch("quodeq._cli_evaluation.run", return_value=_fake_evidence()) as r, \
         patch("quodeq._cli_evaluation.run_full") as rf:
        exit_code = _execute_pipeline(args, config, tmp_path / "evi", tmp_path / "eval")
    assert exit_code == 0
    r.assert_called_once()
    rf.assert_not_called()


def test_skip_scoring_does_not_write_merged_json(tmp_path: Path) -> None:
    """PR diff mode: no merged <language>_evidence.json file in the evidence dir."""
    args = _args(tmp_path)
    config = _config(skip_scoring=True)
    evidence_dir = tmp_path / "evi"
    evidence_dir.mkdir()
    with patch("quodeq._cli_evaluation.run", return_value=_fake_evidence()):
        _execute_pipeline(args, config, evidence_dir, tmp_path / "eval")
    assert not (evidence_dir / "python_evidence.json").exists()


def test_scoring_enabled_calls_run_full(tmp_path: Path) -> None:
    """Baseline: normal mode calls run_full (scoring)."""
    args = _args(tmp_path)
    config = _config(skip_scoring=False)
    with patch("quodeq._cli_evaluation.run") as r, \
         patch("quodeq._cli_evaluation.run_full", return_value={}) as rf:
        exit_code = _execute_pipeline(args, config, tmp_path / "evi", tmp_path / "eval")
    assert exit_code == 0
    rf.assert_called_once()


def test_evidence_only_writes_merged_json(tmp_path: Path) -> None:
    """Baseline: --evidence-only still writes the merged JSON file (existing behavior)."""
    args = _args(tmp_path)
    args.evidence_only = True
    config = _config(skip_scoring=False)
    evidence_dir = tmp_path / "evi"
    evidence_dir.mkdir()
    with patch("quodeq._cli_evaluation.run", return_value=_fake_evidence()):
        _execute_pipeline(args, config, evidence_dir, tmp_path / "eval")
    assert (evidence_dir / "python_evidence.json").exists()
