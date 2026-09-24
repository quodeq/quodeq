"""Tests for shared repo format detection: check_repo_format and read_state."""
import json
import subprocess

from quodeq.data.fs.shared_repo import (
    FORMAT_NAME,
    MARKER_FILENAME,
    RepoFormat,
    bootstrap_repo_layout,
    check_repo_format,
    ensure_shared_clone,
    read_state,
    shared_repo_path,
)


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
    """read_state must not treat "has an evaluations/ dir" as a
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
    """read_state must surface all four check_repo_format outcomes
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


def test_check_repo_format_returns_the_enum_member(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert check_repo_format(repo) is RepoFormat.EMPTY
    bootstrap_repo_layout(repo)
    assert check_repo_format(repo) is RepoFormat.OK


def test_read_state_missing_is_the_enum_member_and_serializes_as_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    state = read_state("file:///nonexistent/repo.git")
    assert state is RepoFormat.MISSING
    assert json.dumps({"repoState": state}) == '{"repoState": "missing"}'
    assert state not in (RepoFormat.OK, RepoFormat.EMPTY)
