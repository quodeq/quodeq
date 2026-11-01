"""Analysis CLIs with bypassed approvals run inside the OS sandbox."""
from pathlib import Path

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, analysis_sandbox_prefix
from quodeq.shared import os_sandbox


def test_provider_without_sandbox_spec_runs_unwrapped(tmp_path):
    prefix, cleanup = analysis_sandbox_prefix(AnalysisConfig(), {}, tmp_path, "claude")
    assert prefix == []
    cleanup()


@pytest.fixture
def captured(tmp_path, monkeypatch):
    seen: dict = {}

    def fake_prefix(**kwargs):
        seen.update(kwargs)
        return ["sandbox-exec", "-f", "p.sb"], lambda: None

    monkeypatch.setattr("quodeq.analysis._cli_sandbox.external_sandbox_prefix", fake_prefix)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evals"))
    return seen


def _run(tmp_path, spec, env=None):
    cfg = AnalysisConfig(jsonl_file=tmp_path / "evals" / "proj" / "run1" / "evidence" / "q_evidence.jsonl")
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    return analysis_sandbox_prefix(cfg, {"analysis_sandbox": spec}, repo, "codex", env)


def test_sandboxed_provider_gets_repo_readable_and_project_writable(tmp_path, captured):
    prefix, _ = _run(tmp_path, {"cli_home": ".codex-test"})
    assert prefix[0] == "sandbox-exec"
    assert str((tmp_path / "repo").resolve()) in captured["readable_home_dirs"]
    assert str((tmp_path / "evals" / "proj").resolve()) in captured["writable_dirs"]
    assert str(tmp_path / ".codex-test") in captured["writable_dirs"]


def test_quodeq_state_outside_the_project_is_not_granted(tmp_path, captured):
    _run(tmp_path, {"cli_home": ".codex-test"})
    granted = [*captured["writable_dirs"], *captured["readable_home_dirs"]]
    assert str(tmp_path / ".quodeq") not in granted
    assert str((tmp_path / "evals").resolve()) not in granted


def test_cli_home_follows_the_env_var_quodeq_set(tmp_path, captured):
    home = tmp_path / "state" / "codex"
    _run(tmp_path, {"cli_home_env": "CODEX_HOME", "cli_home": ".codex-test"}, {"CODEX_HOME": str(home)})
    assert str(home) in captured["writable_dirs"]
    assert str(tmp_path / ".codex-test") not in captured["writable_dirs"]


def test_loopback_is_blocked_except_a_local_proxy(tmp_path, captured):
    _run(tmp_path, {"cli_home": ".x"}, {"HTTPS_PROXY": "http://127.0.0.1:3128"})
    assert captured["block_loopback"] is True
    assert captured["loopback_allow_ports"] == [3128]


def test_sandboxed_provider_fails_closed_without_a_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(os_sandbox.platform, "system", lambda: "Windows")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="sandbox"):
        analysis_sandbox_prefix(
            AnalysisConfig(), {"analysis_sandbox": {"cli_home": ".x"}}, tmp_path, "codex")
