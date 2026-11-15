"""Codex scans use Codex's own sandbox where a probe shows it works."""
import json
import subprocess
from pathlib import Path

import pytest

from quodeq.analysis import codex_sandbox
from quodeq.analysis.subprocess import AnalysisConfig, confine_cli

_BYPASS = "--dangerously-bypass-approvals-and-sandbox"


def test_native_args_swap_the_bypass_and_approve_the_findings_tools():
    args = ["codex", "exec", "--json", _BYPASS, "-c", 'mcp_servers.findings={command = "py", args = []}']
    out = codex_sandbox.native_args(args, ["-c", "x=1"])
    assert _BYPASS not in out
    assert out[out.index("-s") + 1] == "read-only"
    assert out[-1].endswith('default_tools_approval_mode = "approve"}')


def test_profile_blocks_home_and_reads_back_the_given_dirs(tmp_path):
    home, repo = tmp_path, tmp_path / "repo"
    profile = codex_sandbox.profile_args(home, [repo])
    filesystem = next(a for a in profile if a.startswith("permissions.quodeq_scan.filesystem="))
    assert f"{json.dumps(str(home))} = \"none\"" in filesystem  # TOML-escaped, Windows too
    assert f"{json.dumps(str(repo))} = \"read\"" in filesystem
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


def test_windows_probe_runs_each_command_inside_the_sandbox(monkeypatch, tmp_path, installed_cli):
    # npm's codex.cmd goes through cmd.exe: a "&&" would run its right side unconfined.
    monkeypatch.setattr(codex_sandbox.platform, "system", lambda: "Windows")
    calls: list = []
    run = _fake_run("0.162.1", 0)
    monkeypatch.setattr(codex_sandbox.subprocess, "run", lambda argv, **kw: calls.append(argv) or run(argv))
    assert codex_sandbox.native_sandbox_works("codex", ["-c", "w=1"], tmp_path, tmp_path / "f", {})
    probes = [argv[argv.index("--") + 1:] for argv in calls if "--" in argv]
    assert [p[2] for p in probes] == ["dir", "type"]
    assert not any("&&" in p for p in probes)


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


def test_confine_cli_falls_back_to_plain_read_only_when_home_limits_are_refused(tmp_path, monkeypatch):
    # Windows without the elevated sandbox backend refuses restricted reads.
    plain = codex_sandbox.plain_read_only_args()
    args = _scan(tmp_path, monkeypatch, works=True)  # sets up the layout
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works",
                        lambda binary, profile, *a: profile == plain)
    cfg = AnalysisConfig(jsonl_file=tmp_path / "evals" / "p" / "r" / "evidence" / "s_evidence.jsonl")
    spec = {"native_sandbox": True, "analysis_sandbox": {"cli_home": ".codex-test"}}
    args, _ = confine_cli(cfg, spec, tmp_path / "repo", ["codex", "exec", _BYPASS], {})
    assert args[args.index("-s") + 1] == "read-only"
    assert not any(a.startswith("default_permissions") for a in args)


def _probed(tmp_path, monkeypatch, files: dict[str, str]):
    """Scan a repo holding *files* behind a probe that, like the real one,
    passes only when the sample it is given prints something. Returns the
    confined argv and the samples the probe saw."""
    samples: list[Path] = []

    def probe(_binary, _profile, _listed, sample, *_rest):
        samples.append(sample)
        return sample.is_file() and sample.stat().st_size > 0

    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works", probe)
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.external_sandbox_prefix",
                        lambda **kw: (["sandbox-exec", "-f", "p.sb"], lambda: None))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evals"))
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    cfg = AnalysisConfig(jsonl_file=tmp_path / "evals" / "p" / "r" / "evidence" / "s_evidence.jsonl")
    spec = {"native_sandbox": True, "analysis_sandbox": {"cli_home": ".codex-test"}}
    args, _ = confine_cli(cfg, spec, repo, ["codex", "exec", _BYPASS], {})
    return args, samples


def test_an_empty_first_file_does_not_switch_codex_to_the_bypass(tmp_path, monkeypatch):
    args, samples = _probed(tmp_path, monkeypatch, {".aaa": "", ".gitkeep": "", "app.py": "x = 1\n"})
    assert _BYPASS not in args and args[0] == "codex"
    assert samples[0].name == "app.py"


def test_a_repo_with_files_only_in_subfolders_keeps_codex_sandbox(tmp_path, monkeypatch):
    args, samples = _probed(tmp_path, monkeypatch, {"src/pkg/app.py": "x = 1\n"})
    assert _BYPASS not in args
    assert samples[0].name == "app.py"


def test_a_repo_with_nothing_to_sample_is_probed_with_quodeq_own_file(tmp_path, monkeypatch):
    args, samples = _probed(tmp_path, monkeypatch, {".gitkeep": "", ".env": "TOKEN=1\n"})
    assert _BYPASS not in args
    assert samples[0] == Path(codex_sandbox.__file__).resolve()


def test_an_empty_repo_keeps_codex_sandbox(tmp_path, monkeypatch):
    args, _ = _probed(tmp_path, monkeypatch, {})
    assert _BYPASS not in args


def test_probe_sample_never_follows_a_link_out_of_the_repo(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside.txt"
    repo.mkdir()
    outside.write_text("not the repo's\n")
    try:
        (repo / "aaa").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks need a privilege on this machine")
    (repo / "zzz.py").write_text("x = 1\n")
    assert codex_sandbox.probe_sample(repo) == repo / "zzz.py"


def test_probe_sample_skips_what_a_repo_could_use_to_fail_the_probe(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a&b.txt").write_text("cmd.exe would act on this name\n")
    (repo / "big.bin").write_bytes(b"x" * (codex_sandbox.SAMPLE_MAX_BYTES + 1))
    (repo / "id_rsa").write_text("a credential file\n")
    (repo / "ok.txt").write_text("fine\n")
    assert codex_sandbox.probe_sample(repo) == repo / "ok.txt"


def test_probe_sample_stops_looking_after_its_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_sandbox, "SAMPLE_SCAN_LIMIT", 3)
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("a", "b", "c", "d"):
        (repo / name).write_text("")
    (repo / "e.py").write_text("x = 1\n")
    assert codex_sandbox.probe_sample(repo) == Path(codex_sandbox.__file__).resolve()


def test_probe_runs_from_the_given_folder(monkeypatch, tmp_path):
    cwds: list = []
    run = _fake_run("0.162.1", 0)
    monkeypatch.setattr(codex_sandbox.subprocess, "run",
                        lambda argv, **kw: cwds.append(kw.get("cwd")) or run(argv))
    sample = tmp_path / "elsewhere" / "f"
    assert codex_sandbox.native_sandbox_works("codex", ["-c", "cwd=1"], tmp_path, sample, {}, tmp_path)
    assert cwds[-1] == tmp_path
