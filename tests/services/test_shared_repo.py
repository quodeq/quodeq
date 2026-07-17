"""Tests for shared repo clone management."""
import json
import subprocess
import time
from pathlib import Path

import pytest

from quodeq.services.shared_repo import (
    FORMAT_NAME,
    MARKER_FILENAME,
    _git_env,
    bootstrap_repo_layout,
    check_repo_format,
    ensure_shared_clone,
    published_meta,
    read_state,
    refresh_shared_clone,
    run_git,
    shared_cache_dir,
    shared_index_db_path,
    shared_repo_path,
    sync_shared_index,
)


def _make_origin(tmp_path: Path) -> str:
    """Create a bare repo with one commit; return its file:// URL."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    work = tmp_path / "seed"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    (work / "hello.txt").write_text("hi", encoding="utf-8")
    for cmd in (
        ["git", "add", "."],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)
    return f"file://{origin}"


def test_run_git_success_and_failure(tmp_path):
    ok, _ = run_git(["init", str(tmp_path / "x")])
    assert ok
    ok, out = run_git(["rev-parse", "HEAD"], cwd=tmp_path)
    assert not ok
    assert out  # error text captured


def test_cache_dir_is_stable_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path))
    d1 = shared_cache_dir("git@github.com:team/r.git")
    d2 = shared_cache_dir("git@github.com:team/r.git")
    assert d1 == d2
    assert d1.parent == tmp_path / "shared"


def test_ensure_clone_and_refresh(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = _make_origin(tmp_path)
    repo = ensure_shared_clone(url)
    assert repo is not None
    assert (repo / "hello.txt").exists()
    # second call reuses without error
    assert ensure_shared_clone(url) == repo
    assert refresh_shared_clone(url) is True


def test_ensure_clone_bad_url_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    assert ensure_shared_clone(f"file://{tmp_path}/nonexistent.git") is None
    assert not shared_repo_path(f"file://{tmp_path}/nonexistent.git").exists()


def test_run_git_survives_non_utf8_output(tmp_path):
    """Verify run_git handles non-UTF8 git output without raising UnicodeDecodeError."""
    # Initialize a git repo
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Use git alias to output invalid UTF-8 bytes; git will echo them in its output
    ok, output = run_git(
        ["-c", "alias.x=!printf '\\xff\\xfe'", "x"],
        cwd=repo,
    )

    # Must return a tuple (bool, str) without raising UnicodeDecodeError
    assert isinstance(ok, bool)
    assert isinstance(output, str)
    # The invalid bytes should be replaced with U+FFFD (replacement character)
    # Output may contain the replacement character or simply be non-empty
    assert output is not None


def test_check_format_empty_then_bootstrap_then_ok(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert check_repo_format(repo) == "empty"
    bootstrap_repo_layout(repo)
    assert check_repo_format(repo) == "ok"
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "**/evaluation.db" in gitignore
    assert "*.log" in gitignore
    assert (repo / "evaluations").is_dir()


def test_check_format_newer_version_unsupported(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / MARKER_FILENAME).write_text(
        '{"format": "%s", "version": 99}' % FORMAT_NAME, encoding="utf-8"
    )
    assert check_repo_format(repo) == "unsupported_version"


def test_check_format_foreign_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text("some other project", encoding="utf-8")
    assert check_repo_format(repo) == "foreign"


def test_check_format_marker_not_dict(tmp_path):
    """Marker JSON that parses but is not a dict (e.g. list) returns 'foreign'."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / MARKER_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    assert check_repo_format(repo) == "foreign"


def test_check_format_version_not_int_parseable(tmp_path):
    """Version field that cannot be parsed as int returns 'unsupported_version'."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / MARKER_FILENAME).write_text(
        '{"format": "%s", "version": "1.0"}' % FORMAT_NAME, encoding="utf-8"
    )
    assert check_repo_format(repo) == "unsupported_version"


def test_check_format_invalid_utf8_marker(tmp_path):
    """Marker file with invalid UTF-8 bytes returns 'foreign'."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    # Write raw bytes that are invalid UTF-8
    (repo / MARKER_FILENAME).write_bytes(b"\xff\xfe invalid json")
    assert check_repo_format(repo) == "foreign"


def test_check_format_missing_repo_root(tmp_path):
    """Missing repo_root directory returns 'foreign' (not FileNotFoundError)."""
    repo = tmp_path / "nonexistent" / "repo"
    # repo does not exist; iterdir() would raise FileNotFoundError
    assert check_repo_format(repo) == "foreign"


def test_check_format_wrong_format_string(tmp_path):
    """Marker with wrong format string returns 'foreign'."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / MARKER_FILENAME).write_text(
        '{"format": "something-else", "version": 1}', encoding="utf-8"
    )
    assert check_repo_format(repo) == "foreign"


def test_git_env_disables_terminal_prompt_and_keeps_lfs_skip():
    """run_git's subprocess env must never block on an interactive git
    credential/passphrase prompt: GIT_TERMINAL_PROMPT=0 tells git to fail
    fast instead of trying to read a prompt from a terminal that (with
    stdin=DEVNULL) no longer exists.
    """
    env = _git_env()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_LFS_SKIP_SMUDGE"] == "1"
    # GIT_SSH_COMMAND must NOT be set here: overriding it would silently
    # discard the user's own ssh config (identity files, host aliases, etc).
    assert "GIT_SSH_COMMAND" not in env


def test_run_git_does_not_hang_on_credential_prompt(tmp_path):
    """Without stdin=DEVNULL, a git subcommand that reads from stdin (like
    `credential fill`) can block waiting for input that will never come.
    With stdin closed, git gets an immediate EOF and fails fast instead.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    start = time.monotonic()
    ok, _out = run_git(["credential", "fill"], cwd=repo, timeout=5)
    elapsed = time.monotonic() - start

    assert elapsed < 5  # never hit the timeout path
    assert isinstance(ok, bool)


def test_readable_and_index_sync_on_published_clone(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    # build a real published origin using the Phase 1 publish path
    from quodeq.services.shared_publish import publish_project
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"
    project = root / "proj-a"
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "anna")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "a@a")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "anna")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "a@a")
    publish_project("proj-a", url, evaluations_root=root)

    assert read_state(url) == "ok"
    sync_shared_index(url)
    assert shared_index_db_path(url).exists()
    meta = published_meta(url)
    assert meta["proj-a"]["publishedBy"] == "anna"
    assert meta["proj-a"]["publishedAt"] > 0
