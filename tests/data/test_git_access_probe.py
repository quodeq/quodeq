"""probe_remote: fast, prompt-free reachability check with a classified answer."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from quodeq.config.clone_env import git_probe_timeout_s
from quodeq.data.fs.git_access_probe import MIN_GIT_VERSION, ProbeResult, git_version, probe_remote
from quodeq.shared.git_errors import GitFailureKind

_URL = "https://github.com/o/r.git"


def _fake_run(*, returncode=0, stdout="", stderr="", version="git version 2.50.1", raise_exc=None):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[1] == "--version":
            return SimpleNamespace(returncode=0, stdout=version, stderr="")
        if raise_exc is not None:
            raise raise_exc
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    run.calls = calls
    return run


def test_ok_when_ls_remote_succeeds():
    run = _fake_run(stdout="abc\trefs/heads/main\n")
    assert probe_remote(_URL, env={}, run=run) == ProbeResult(GitFailureKind.OK)
    argv, kwargs = run.calls[-1]
    assert argv[1:5] == ["ls-remote", "--exit-code", "--heads", "--"]
    assert argv[-1] == _URL
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["timeout"] == git_probe_timeout_s({})


def test_empty_repository_counts_as_ok():
    # --exit-code answers 2 when there are no matching refs: a fresh repo.
    assert probe_remote(_URL, env={}, run=_fake_run(returncode=2)).kind is GitFailureKind.OK


def test_private_repo_without_access_is_not_found_with_detail():
    stderr = "remote: Repository not found.\nfatal: repository 'https://github.com/o/r.git/' not found\n"
    result = probe_remote(_URL, env={}, run=_fake_run(returncode=128, stderr=stderr))
    assert result.kind is GitFailureKind.NOT_FOUND
    assert result.detail.endswith("not found")


def test_auth_required_when_prompts_are_disabled():
    stderr = "fatal: could not read Username for 'https://github.com': terminal prompts disabled\n"
    assert probe_remote(_URL, env={}, run=_fake_run(returncode=128, stderr=stderr)).kind is GitFailureKind.AUTH_REQUIRED


def test_timeout_has_no_detail():
    run = _fake_run(raise_exc=subprocess.TimeoutExpired(cmd=["git"], timeout=15))
    assert probe_remote(_URL, env={}, run=run) == ProbeResult(GitFailureKind.TIMEOUT, "")


def test_git_missing():
    def run_missing(argv, **kwargs):
        raise FileNotFoundError("git")

    assert probe_remote(_URL, env={}, run=run_missing) == ProbeResult(GitFailureKind.GIT_MISSING, "")


def test_old_git_is_reported_before_probing():
    run = _fake_run(version="git version 2.20.1")
    result = probe_remote(_URL, env={}, run=run)
    assert result.kind is GitFailureKind.GIT_TOO_OLD
    assert "2.20" in result.detail
    assert len(run.calls) == 1  # only --version ran


def test_access_env_reaches_the_probe():
    run = _fake_run()
    probe_remote(_URL, env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "k", "GIT_CONFIG_VALUE_0": "v"}, run=run)
    assert run.calls[-1][1]["env"]["GIT_CONFIG_COUNT"] == "1"


@pytest.mark.parametrize("text,expected", [
    ("git version 2.50.1 (Apple Git-155)", (2, 50)),
    ("git version 2.31.0", (2, 31)),
    ("nonsense", None),
])
def test_git_version_parses(text, expected):
    assert git_version(env={}, run=_fake_run(version=text)) == expected
    assert MIN_GIT_VERSION == (2, 31)


def test_probe_timeout_env(monkeypatch):
    assert git_probe_timeout_s({}) == 15
    assert git_probe_timeout_s({"QUODEQ_GIT_PROBE_TIMEOUT_S": "40"}) == 40
    assert git_probe_timeout_s({"QUODEQ_GIT_PROBE_TIMEOUT_S": "0"}) == 15


def test_git_config_entries_prefix_the_argv_as_c_pairs():
    pin = "http.curloptResolve=github.com:443:140.82.121.3"
    run = _fake_run()
    probe_remote(_URL, env={}, run=run, git_config=[pin])
    argv, _ = run.calls[-1]
    assert argv[1:4] == ["-c", pin, "ls-remote"]
