"""Scan agents cannot read the repo's credential files, and committed ones are still reported."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.analysis import codex_sandbox
from quodeq.analysis.checks.registry import CHECKERS, CheckContext
from quodeq.analysis.subprocess import AnalysisConfig, SandboxPolicy, build_ai_cmd, confine_cli
from quodeq.shared import os_sandbox
from tests.core._fake_secrets import GENERIC_VALUE

_BYPASS = "--dangerously-bypass-approvals-and-sandbox"


def _entry(path, access):
    return f"{json.dumps(str(path))} = \"{access}\""  # TOML escapes Windows backslashes


def test_claude_scan_denies_reading_credential_files(tmp_path):
    config = AnalysisConfig(
        ai_cmd="claude", ai_model="sonnet-4", compiled_dir=tmp_path, dimension="security",
        jsonl_file=tmp_path / "evidence" / "security_evidence.jsonl",
    )
    args, _ = build_ai_cmd("Analyze", config)
    denied = args[args.index("--disallowedTools") + 1].split(",")
    assert {"Read(./**/.env)", "Read(./**/*.pem)", "Read(./**/id_rsa)"} <= set(denied)


def test_codex_profile_denies_files_inside_a_readable_repo(tmp_path):
    profile = codex_sandbox.profile_args(tmp_path, [tmp_path / "repo"], [tmp_path / "repo" / ".env"])
    filesystem = next(a for a in profile if ".filesystem=" in a)
    assert _entry(tmp_path / "repo", "read") in filesystem
    assert _entry(tmp_path / "repo" / ".env", "none") in filesystem


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evals"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("TOKEN=x\n")  # sorts first: must not be the probe's sample
    (repo / "app.py").write_text("x = 1\n")
    return repo


def _confine(tmp_path, repo, policy=SandboxPolicy()):
    cfg = AnalysisConfig(jsonl_file=tmp_path / "evals" / "p" / "r" / "evidence" / "s_evidence.jsonl")
    spec = {"native_sandbox": True, "analysis_sandbox": {"cli_home": ".codex-test"}}
    return confine_cli(cfg, spec, repo, ["codex", "exec", _BYPASS], {}, policy)[0]


@pytest.fixture
def warnings(monkeypatch):
    monkeypatch.setattr("quodeq.analysis._cli_sandbox._warned_unsandboxed", set())
    monkeypatch.setattr("quodeq.analysis._cli_sandbox._warned_secrets_readable", set())
    messages: list[str] = []
    return messages, SandboxPolicy(log=SimpleNamespace(warning=messages.append))


def test_codex_native_sandbox_denies_the_repo_secret_files(tmp_path, repo, monkeypatch):
    probes: list = []
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works",
                        lambda binary, profile, listed, sample, env: probes.append(sample) or True)
    args = _confine(tmp_path, repo)
    assert probes == [(repo / "app.py").resolve()]
    assert _entry((repo / ".env").resolve(), "none") in next(a for a in args if ".filesystem=" in a)


def test_codex_keeps_plain_read_only_where_it_cannot_deny_files(tmp_path, repo, monkeypatch):
    plain = codex_sandbox.plain_read_only_args()
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works",
                        lambda binary, profile, *a: profile == plain)
    args = _confine(tmp_path, repo)
    assert args[args.index("-s") + 1] == "read-only"


def test_codex_says_when_its_sandbox_cannot_hide_the_credential_files(tmp_path, repo, monkeypatch,
                                                                     warnings):
    plain = codex_sandbox.plain_read_only_args()
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works",
                        lambda binary, profile, *a: profile == plain)
    messages, policy = warnings
    _confine(tmp_path, repo, policy)
    _confine(tmp_path, repo, policy)  # every agent of the run: one warning
    [message] = messages
    assert "cannot hide single files" in message and "credential files: .env." in message


def test_codex_stays_quiet_when_it_hides_the_credential_files(tmp_path, repo, monkeypatch, warnings):
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works", lambda *a: True)
    messages, policy = warnings
    _confine(tmp_path, repo, policy)
    assert messages == []


def test_running_without_a_sandbox_names_the_readable_credential_files(tmp_path, repo, monkeypatch,
                                                                       warnings):
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works", lambda *a: False)
    monkeypatch.setattr(os_sandbox.platform, "system", lambda: "Windows")
    for i in range(4):
        (repo / f"k{i}.pem").write_text("x")
    messages, policy = warnings
    _confine(tmp_path, repo, policy)
    [message] = messages
    assert "without an OS sandbox" in message
    assert "credential files: .env, k0.pem, k1.pem and 2 more." in message


def test_os_sandbox_gets_the_repo_secret_files(tmp_path, repo, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.native_sandbox_works", lambda *a: False)
    monkeypatch.setattr("quodeq.analysis._cli_sandbox.external_sandbox_prefix",
                        lambda **kw: seen.update(kw) or (["sandbox-exec"], lambda: None))
    _confine(tmp_path, repo)
    assert seen["unreadable_files"] == [str(repo / ".env")]


def test_hardcoded_secrets_check_reports_committed_credential_files(tmp_path):
    context = CheckContext(
        root=tmp_path, source_files=("app.py",), dimension="security",
        text_reader=lambda root, paths: [("app.py", "x = 1\n")],
        secret_file_reader=lambda root: [(".env", "assignments", f"API_KEY={GENERIC_VALUE}\n")],
    )
    [found] = CHECKERS["hardcoded-secrets"](context)
    assert (found.file, found.violation_type) == (".env", "committed-secret-file")
