"""Tests for shared repo clone management."""
import subprocess
from pathlib import Path

from quodeq.services.shared_repo import (
    ensure_shared_clone,
    refresh_shared_clone,
    run_git,
    shared_cache_dir,
    shared_repo_path,
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
