"""Codex scans use Codex's own sandbox where a probe shows it works."""
import subprocess
from pathlib import Path

from quodeq.analysis import codex_sandbox
from quodeq.analysis.subprocess import AnalysisConfig, confine_cli

_BYPASS = "--dangerously-bypass-approvals-and-sandbox"


def test_native_args_swap_the_bypass_and_approve_the_findings_tools():
    args = ["codex", "exec", "--json", _BYPASS, "-c", 'mcp_servers.findings={command = "py", args = []}']
    out = codex_sandbox.native_args(args, ["-c", "x=1"])
    assert _BYPASS not in out
    assert out[out.index("-s") + 1] == "read-only"
    assert out[-1].endswith('default_tools_approval_mode = "approve"}')


def test_profile_blocks_home_and_reads_back_the_given_dirs():
    profile = codex_sandbox.profile_args(Path("/home/u"), [Path("/home/u/repo")])
    filesystem = next(a for a in profile if a.startswith("permissions.quodeq_scan.filesystem="))
    assert '"/home/u" = "none"' in filesystem
    assert '"/home/u/repo" = "read"' in filesystem
    assert 'approval_policy="never"' in profile


def _fake_run(version: str, probe_rc: int):
    def run(argv, **_):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=f"codex-cli {version}\n")
        return subprocess.CompletedProcess(argv, probe_rc, stdout=b"contents")
    return run


def test_probe_rejects_a_codex_older_than_tested(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_sandbox.subprocess, "run", _fake_run("0.150.0", 0))
    assert not codex_sandbox.native_sandbox_works("codex", [], tmp_path, tmp_path / "f", {})


def test_probe_rejects_a_sandbox_that_fails_here(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_sandbox.subprocess, "run", _fake_run("0.162.1", 1))
    assert not codex_sandbox.native_sandbox_works("codex", [], tmp_path, tmp_path / "f", {})


def _scan(tmp_path, monkeypatch, works: bool):
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works", lambda *a: works)
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.external_sandbox_prefix",
                        lambda **kw: (["sandbox-exec", "-f", "p.sb"], lambda: None))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evals"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    cfg = AnalysisConfig(jsonl_file=tmp_path / "evals" / "p" / "r" / "evidence" / "s_evidence.jsonl")
    spec = {"native_sandbox": True, "analysis_sandbox": {"cli_home": ".codex-test"}}
    args, _ = confine_cli(cfg, spec, repo, ["codex", "exec", _BYPASS], {})
    return args


def test_confine_cli_uses_codex_sandbox_when_the_probe_passes(tmp_path, monkeypatch):
    args = _scan(tmp_path, monkeypatch, works=True)
    assert args[0] == "codex" and _BYPASS not in args


def test_confine_cli_falls_back_to_the_os_sandbox(tmp_path, monkeypatch):
    args = _scan(tmp_path, monkeypatch, works=False)
    assert args[0] == "sandbox-exec" and _BYPASS in args
