"""Tests for shared repo clone management: run_git, clone/refresh and clone-dir removal."""
import subprocess
import time
from pathlib import Path

from quodeq.data.fs.shared_repo import (
    _git_env,
    ensure_shared_clone,
    refresh_shared_clone,
    remove_clone_dir,
    run_git,
    shared_cache_dir,
    shared_repo_path,
)
from tests.data._shared_repo_helpers import _make_origin


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
    ok, reason = refresh_shared_clone(url)
    assert ok is True
    assert reason == ""


def test_clone_and_refresh_are_not_shallow(tmp_path, monkeypatch):
    """A permanently-shallow (--depth 1) clone means
    `git log -1 -- path` on the shallow root commit attributes EVERY path
    to the tip commit, misattributing every project except the most
    recently pushed one. Both the initial clone and the refresh fetch must
    pull full history -- neither leaves a .git/shallow marker behind."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = _make_origin(tmp_path)
    repo = ensure_shared_clone(url)
    assert repo is not None
    assert not (repo / ".git" / "shallow").exists()
    ok, _ = refresh_shared_clone(url)
    assert ok is True
    assert not (repo / ".git" / "shallow").exists()


def test_refresh_shared_clone_passes_explicit_timeout_to_both_git_calls(tmp_path, monkeypatch):
    """Finding 4 regression: refresh_shared_clone must not inherit run_git's
    300s default -- it's called in-request (GET /api/shared/projects?refresh=1,
    POST /api/shared/refresh) and a black-holed connection would otherwise
    hang the request for up to 5 minutes. A tiny explicit *timeout* must
    reach BOTH the fetch (network) and reset (local) run_git calls."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = _make_origin(tmp_path)
    assert ensure_shared_clone(url) is not None

    seen_timeouts: list[int] = []
    real_run_git = run_git

    def _spy(args, *, cwd=None, timeout=None):
        seen_timeouts.append(timeout)
        return real_run_git(args, cwd=cwd, timeout=timeout)

    monkeypatch.setattr("quodeq.data.fs.shared_repo.run_git", _spy)

    ok, _ = refresh_shared_clone(url, timeout=7)
    assert ok is True
    assert seen_timeouts == [7, 7]


def test_refresh_shared_clone_default_timeout_is_bounded_not_300s(tmp_path, monkeypatch):
    """Without an explicit timeout, refresh_shared_clone must still use a
    short bounded default (not run_git's 300s general-purpose default)."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = _make_origin(tmp_path)
    assert ensure_shared_clone(url) is not None

    seen_timeouts: list[int] = []
    real_run_git = run_git

    def _spy(args, *, cwd=None, timeout=None):
        seen_timeouts.append(timeout)
        return real_run_git(args, cwd=cwd, timeout=timeout)

    monkeypatch.setattr("quodeq.data.fs.shared_repo.run_git", _spy)

    ok, _ = refresh_shared_clone(url)
    assert ok is True
    assert seen_timeouts == [30, 30]


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


def test_refresh_shared_clone_returns_reason_on_fetch_failure(tmp_path, monkeypatch, caplog):
    """refresh_shared_clone must surface WHY a refresh
    failed (the git stderr tail), not just False -- without it, the UI can
    only render "Request failed: 502" for DNS failure vs auth failure vs a
    deleted origin. The failure must also be logged via logger.warning so a
    caller that discards the reason (e.g. publish_project's best-effort
    refresh) still leaves a diagnosable server-side trail."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = _make_origin(tmp_path)
    assert ensure_shared_clone(url) is not None

    # The origin becomes unreachable, as if it had been deleted.
    origin_path = Path(url.removeprefix("file://"))
    origin_path.rename(tmp_path / "origin-gone.git")

    with caplog.at_level("WARNING"):
        ok, reason = refresh_shared_clone(url)

    assert ok is False
    assert reason  # non-empty
    assert len(reason) <= 200
    assert caplog.text  # logged via logger.warning, not silently swallowed


def test_refresh_shared_clone_success_returns_empty_reason(tmp_path, monkeypatch):
    """The reason string is "" on a successful refresh (no error to report)."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = _make_origin(tmp_path)
    assert ensure_shared_clone(url) is not None

    ok, reason = refresh_shared_clone(url)
    assert ok is True
    assert reason == ""


# --- remove_clone_dir: Windows-safe deletion of git trees ---------------
# Git marks object files read-only. POSIX deletion only checks the parent
# dir, but on Windows rmtree raises PermissionError on them, so plain
# rmtree fails (test suite) or silently leaves .git debris behind
# (ignore_errors=True in disconnect, corrupting a later reconnect).


def test_remove_clone_dir_deletes_tree_with_readonly_files(tmp_path):
    """A tree holding read-only files (git objects) is fully removed."""
    tree = tmp_path / "repo"
    objects = tree / ".git" / "objects" / "09"
    objects.mkdir(parents=True)
    blob = objects / "abc123"
    blob.write_bytes(b"x")
    blob.chmod(0o444)

    remove_clone_dir(tree)

    assert not tree.exists()


def test_remove_clone_dir_missing_path_is_noop(tmp_path):
    remove_clone_dir(tmp_path / "never-created")


def test_remove_clone_dir_never_raises_on_persistent_failure(tmp_path, caplog, monkeypatch):
    """If chmod+retry also fails, the error is logged, not raised (a
    permission-denied cache dir must not turn a disconnect into a 500)."""
    import os as _os

    tree = tmp_path / "repo"
    tree.mkdir()
    (tree / "f").write_bytes(b"x")

    real_unlink = _os.unlink

    def deny_unlink(path, *a, **kw):
        if Path(path).name == "f":
            raise PermissionError(5, "Access is denied", str(path))
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(_os, "unlink", deny_unlink)
    with caplog.at_level("WARNING"):
        remove_clone_dir(tree)  # must not raise

    assert "failed to remove" in caplog.text
