"""Tests for shared repo clone management."""
import json
import shutil
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
    shared_evaluations_root,
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
    ok, reason = refresh_shared_clone(url)
    assert ok is True
    assert reason == ""


def test_clone_and_refresh_are_not_shallow(tmp_path, monkeypatch):
    """Audit finding C1: a permanently-shallow (--depth 1) clone means
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

    monkeypatch.setattr("quodeq.services.shared_repo.run_git", _spy)

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

    monkeypatch.setattr("quodeq.services.shared_repo.run_git", _spy)

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
    # publishedBy (published.json) comes from `git config user.name` in the
    # clone, not from GIT_AUTHOR_NAME/GIT_COMMITTER_NAME (those only affect a
    # commit's recorded identity) -- pin it explicitly, on the clone's LOCAL
    # config, so this assertion is deterministic regardless of the machine
    # running the test.
    assert ensure_shared_clone(url) is not None
    subprocess.run(
        ["git", "config", "user.name", "anna"], cwd=shared_repo_path(url), check=True, capture_output=True,
    )
    publish_project("proj-a", url, evaluations_root=root)

    assert read_state(url) == "ok"
    sync_shared_index(url)
    assert shared_index_db_path(url).exists()
    meta = published_meta(url)
    assert meta["proj-a"]["publishedBy"] == "anna"
    assert meta["proj-a"]["publishedAt"] > 0


def test_published_meta_author_name_with_pipe(tmp_path, monkeypatch):
    """Test that author names containing pipes are correctly parsed.

    published_meta now prefers published.json, which round-trips a "|" in a
    JSON string trivially -- so this test drops published.json after
    publishing to force the legacy git-log fallback, which is what this
    test actually targets: `rpartition("|")` in published_meta's git-log
    branch must not misparse a `%an|%ct` line when %an itself contains "|".
    """
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

    # Force the legacy git-log fallback (see docstring).
    (shared_evaluations_root(url) / "proj-pipe" / "published.json").unlink()

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


def _publish_project_as(
    monkeypatch, url: str, root: Path, project_id: str, author: str
) -> None:
    """Publish project_id into the shared repo at url, attributed to author.

    Pre-clones (if needed) and pins the clone's LOCAL git config user.name to
    author before publishing, so published.json's publishedBy (sourced from
    `git config user.name`, not GIT_AUTHOR_NAME/GIT_COMMITTER_NAME) is
    deterministic. Also sets GIT_AUTHOR_NAME/EMAIL and GIT_COMMITTER_NAME/EMAIL
    (via monkeypatch, so they don't leak into other tests) so the underlying
    `git commit` succeeds without needing any git identity configured on the
    machine running the tests.
    """
    from quodeq.services.shared_publish import publish_project

    monkeypatch.setenv("GIT_AUTHOR_NAME", author)
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", f"{author}@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", author)
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", f"{author}@example.com")

    assert ensure_shared_clone(url) is not None
    subprocess.run(
        ["git", "config", "user.name", author], cwd=shared_repo_path(url), check=True, capture_output=True,
    )
    publish_project(project_id, url, evaluations_root=root)


def _make_minimal_project(root: Path, project_id: str) -> None:
    project = root / project_id
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")


def test_published_meta_two_authors_each_keeps_own_attribution(tmp_path, monkeypatch):
    """Regression for audit C1: publishing project B (by a different author,
    later) must not change what published_meta reports for project A. Before
    this fix, the clone was permanently shallow (--depth 1), so `git log -1
    -- path` on project A's path returned the LATEST commit (project B's,
    authored by bob) rather than project A's own commit -- misattributing
    every project except the most recently published one. published.json,
    written at publish time, makes each project's attribution independent of
    any later commit anywhere else in the clone."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"

    _make_minimal_project(root, "proj-a")
    _publish_project_as(monkeypatch, url, root, "proj-a", "alice")

    _make_minimal_project(root, "proj-b")
    _publish_project_as(monkeypatch, url, root, "proj-b", "bob")

    meta = published_meta(url)
    assert meta["proj-a"]["publishedBy"] == "alice"
    assert meta["proj-b"]["publishedBy"] == "bob"


def test_published_meta_legacy_fallback_correct_per_path_author_with_full_history(tmp_path, monkeypatch):
    """THE regression test for audit finding C1, verified experimentally:

    `git clone --depth 1` of a remote already holding multiple commits keeps
    only the tip commit, as a parentless ("grafted") commit. A parentless
    commit is diffed against the empty tree, so `git log -- path` treats it
    as having introduced EVERY path present in its snapshot -- including
    paths that were really added by earlier, now-truncated commits. So on a
    shallow clone, `git log -1 -- evaluations/proj-a` incorrectly returns
    whoever authored the LATEST commit (bob, via proj-b), not proj-a's real
    author (alice), for any legacy dir lacking published.json.

    This reproduces that exact scenario: publish proj-a (alice) then proj-b
    (bob) on one clone, force a FRESH re-clone (simulating a cache-recreate
    or a different machine's first connect against the now-multi-commit
    remote -- the only situation where clone shallow-ness actually matters,
    since a single continuously-reused clone's own `git commit` calls always
    keep a genuine full parent chain regardless of the original clone's
    depth), then drop proj-a's published.json from the fresh clone's working
    tree to simulate it predating the published.json feature. Before this
    fix (ensure_shared_clone's `--depth 1`), the fresh clone is shallow and
    proj-a incorrectly resolves to bob. With the fix (full clone), it
    resolves to its true author, alice.
    """
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"

    _make_minimal_project(root, "proj-a")
    _publish_project_as(monkeypatch, url, root, "proj-a", "alice")

    _make_minimal_project(root, "proj-b")
    _publish_project_as(monkeypatch, url, root, "proj-b", "bob")

    # Force a fresh re-clone from origin, which now holds both commits.
    shutil.rmtree(shared_repo_path(url))
    assert ensure_shared_clone(url) is not None

    # Simulate a legacy dir published before published.json existed: drop
    # the file from proj-a's (freshly re-cloned) working tree.
    # published_meta reads it straight off disk, not from git history, so no
    # re-commit is needed to exercise the fallback; proj-b keeps its file.
    (shared_evaluations_root(url) / "proj-a" / "published.json").unlink()

    meta = published_meta(url)
    assert meta["proj-a"]["publishedBy"] == "alice"
    assert meta["proj-b"]["publishedBy"] == "bob"


def test_refresh_shared_clone_unshallows_legacy_cache(tmp_path, monkeypatch):
    """Review finding on commit 09c3dd71: unshallowing only helps NEW clones
    (ensure_shared_clone's `--depth 1` removal). A shared-clone cache
    directory created while the old `--depth 1` code was live stays shallow
    forever: ensure_shared_clone early-returns because `.git` already
    exists, and a plain `fetch origin HEAD` does not unshallow on its own
    (verified live). refresh_shared_clone must detect `.git/shallow` and run
    `git fetch --unshallow origin` first, so a legacy shallow cache
    self-heals on its next refresh instead of keeping the shallow-clone
    misattribution (audit finding C1) forever.
    """
    builder_cache = tmp_path / "builder-cache"
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(builder_cache))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"

    # Two commits by different authors, same fixture shape as the C1
    # regression above: a shallow (grafted-tip) clone attributes every path
    # to bob (the later, tip commit) instead of proj-a's real author alice.
    _make_minimal_project(root, "proj-a")
    _publish_project_as(monkeypatch, url, root, "proj-a", "alice")
    _make_minimal_project(root, "proj-b")
    _publish_project_as(monkeypatch, url, root, "proj-b", "bob")

    # Point QUODEQ_CACHE_ROOT at the real cache root this test targets, and
    # manually build a shallow clone at the EXACT path shared_repo_path(url)
    # expects -- simulating a cache dir created back when ensure_shared_clone
    # still used `git clone --depth 1`.
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    repo = shared_repo_path(url)
    repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(repo)], check=True, capture_output=True,
    )
    assert (repo / ".git" / "shallow").exists()

    ok, _ = refresh_shared_clone(url)
    assert ok is True
    assert not (repo / ".git" / "shallow").exists()

    # Force the legacy git-log fallback for proj-a, AFTER refresh (refresh's
    # own reset --hard would otherwise restore published.json from history,
    # masking the bug this test targets).
    (shared_evaluations_root(url) / "proj-a" / "published.json").unlink()

    meta = published_meta(url)
    assert meta["proj-a"]["publishedBy"] == "alice"


def test_refresh_shared_clone_returns_reason_on_fetch_failure(tmp_path, monkeypatch, caplog):
    """Audit finding B3: refresh_shared_clone must surface WHY a refresh
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
