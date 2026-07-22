"""Tests for shared repo clone management."""
import json
import subprocess
import time
from pathlib import Path

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

    monkeypatch.setattr("quodeq.services.shared_repo.run_git", _spy)

    assert refresh_shared_clone(url, timeout=7) is True
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

    monkeypatch.setattr("quodeq.services.shared_repo.run_git", _spy)

    assert refresh_shared_clone(url) is True
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


def test_published_meta_author_name_with_pipe(tmp_path, monkeypatch):
    """Test that author names containing pipes are correctly parsed."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    from quodeq.services.shared_publish import publish_project
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"
    project = root / "proj-pipe"
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")
    # Author name with pipe character
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Jane | Marketing")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "jane@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Jane | Marketing")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "jane@example.com")
    publish_project("proj-pipe", url, evaluations_root=root)

    meta = published_meta(url)
    assert "proj-pipe" in meta
    assert meta["proj-pipe"]["publishedBy"] == "Jane | Marketing"
    assert isinstance(meta["proj-pipe"]["publishedAt"], int)
    assert meta["proj-pipe"]["publishedAt"] > 0


def test_read_state_missing_clone(tmp_path, monkeypatch):
    """read_state returns 'missing' when clone does not exist."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = "file:///nonexistent/repo.git"
    assert read_state(url) == "missing"


def test_read_state_unsupported_version(tmp_path, monkeypatch):
    """read_state returns 'unsupported_version' when quodeq.json has version > FORMAT_VERSION."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = "file:///dummy/url"
    repo = shared_repo_path(url, {"QUODEQ_CACHE_ROOT": str(tmp_path / "cache")})
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / MARKER_FILENAME).write_text(
        json.dumps({"format": FORMAT_NAME, "version": 99}), encoding="utf-8"
    )
    assert read_state(url) == "unsupported_version"


def test_read_state_foreign_with_evaluations_dir_still_foreign(tmp_path, monkeypatch):
    """Audit A1: read_state must not treat "has an evaluations/ dir" as a
    proxy for "ok" -- that let a real foreign repo (someone else's git repo
    that happens to contain a directory named evaluations/) serve as if it
    were a quodeq clone. A foreign repo is foreign regardless of its
    contents; only the quodeq.json marker (checked by check_repo_format)
    decides "ok"."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    url = "file:///dummy/url"
    repo = shared_repo_path(url, {"QUODEQ_CACHE_ROOT": str(tmp_path / "cache")})
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("Some other project")
    (repo / "evaluations").mkdir()
    assert read_state(url) == "foreign"


def test_read_state_distinguishes_empty_and_foreign(tmp_path, monkeypatch):
    """Audit A1: read_state must surface all four check_repo_format outcomes
    instead of collapsing "empty" and "foreign" down to "missing" -- real
    clones of real local bare origins, not hand-built directories, so the
    full ensure_shared_clone -> read_state path is exercised end to end."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))

    # missing: no clone at all.
    missing_url = "file:///nonexistent/repo-for-state-test.git"
    assert read_state(missing_url) == "missing"

    # empty: a real clone of a bare origin with zero commits.
    empty_origin = tmp_path / "empty-origin.git"
    subprocess.run(["git", "init", "--bare", str(empty_origin)], check=True, capture_output=True)
    empty_url = f"file://{empty_origin}"
    assert ensure_shared_clone(empty_url) is not None
    assert read_state(empty_url) == "empty"

    # foreign: a real clone of a bare origin holding a README but no marker.
    foreign_origin = tmp_path / "foreign-origin.git"
    subprocess.run(["git", "init", "--bare", str(foreign_origin)], check=True, capture_output=True)
    foreign_seed = tmp_path / "foreign-seed"
    subprocess.run(["git", "clone", str(foreign_origin), str(foreign_seed)], check=True, capture_output=True)
    (foreign_seed / "README.md").write_text("some other project", encoding="utf-8")
    for cmd in (
        ["git", "add", "."],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=foreign_seed, check=True, capture_output=True)
    foreign_url = f"file://{foreign_origin}"
    assert ensure_shared_clone(foreign_url) is not None
    assert read_state(foreign_url) == "foreign"

    # ok: marker present via bootstrap_repo_layout on a real clone.
    ok_origin = tmp_path / "ok-origin.git"
    subprocess.run(["git", "init", "--bare", str(ok_origin)], check=True, capture_output=True)
    ok_url = f"file://{ok_origin}"
    ok_repo = ensure_shared_clone(ok_url)
    assert ok_repo is not None
    bootstrap_repo_layout(ok_repo)
    assert read_state(ok_url) == "ok"


def test_published_meta_skips_uncommitted_project_dir(tmp_path, monkeypatch):
    """published_meta skips a project dir with no committed history."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    from quodeq.services.shared_publish import publish_project
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"

    # Create and publish proj-committed
    project_committed = root / "proj-committed"
    run = project_committed / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project_committed / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "alice")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "a@a")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "alice")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "a@a")
    publish_project("proj-committed", url, evaluations_root=root)

    # Create proj-uncommitted dir locally (not committed)
    project_uncommitted = root / "proj-uncommitted"
    (project_uncommitted / "run-1").mkdir(parents=True)
    (project_uncommitted / "repository_info.json").write_text('{"name":"demo"}')

    meta = published_meta(url)
    assert "proj-committed" in meta
    assert "proj-uncommitted" not in meta
