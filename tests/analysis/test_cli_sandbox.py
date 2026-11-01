"""Analysis CLIs with bypassed approvals run inside the OS sandbox."""
from pathlib import Path

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, analysis_sandbox_prefix
from quodeq.shared import os_sandbox


def test_provider_without_sandbox_spec_runs_unwrapped(tmp_path):
    prefix, cleanup = analysis_sandbox_prefix(AnalysisConfig(), {}, tmp_path, "claude")
    assert prefix == []
    cleanup()


def test_sandboxed_provider_gets_repo_readable_and_run_dir_writable(tmp_path, monkeypatch):
    captured = {}

    def fake_prefix(**kwargs):
        captured.update(kwargs)
        return ["sandbox-exec", "-f", "p.sb"], lambda: None

    monkeypatch.setattr("quodeq.analysis._cli_sandbox.external_sandbox_prefix", fake_prefix)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    run_dir = tmp_path / "evals" / "run1"
    cfg = AnalysisConfig(jsonl_file=run_dir / "evidence" / "q_evidence.jsonl")
    repo = tmp_path / "repo"
    repo.mkdir()
    prefix, _ = analysis_sandbox_prefix(
        cfg, {"analysis_sandbox": {"cli_home": ".codex-test"}}, repo, "codex")
    assert prefix[0] == "sandbox-exec"
    assert str(repo.resolve()) in captured["readable_home_dirs"]
    assert str(run_dir.resolve()) in captured["writable_dirs"]
    assert str(tmp_path / ".codex-test") in captured["writable_dirs"]


def test_sandboxed_provider_fails_closed_without_a_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(os_sandbox.platform, "system", lambda: "Windows")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="sandbox"):
        analysis_sandbox_prefix(
            AnalysisConfig(), {"analysis_sandbox": {"cli_home": ".x"}}, tmp_path, "codex")
