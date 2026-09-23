"""Tests for the legacy git-log attribution fallback and shallow-cache self-healing."""
import subprocess
from pathlib import Path

from quodeq.data.fs.shared_repo import (
    published_meta,
    refresh_shared_clone,
    shared_evaluations_root,
    shared_repo_path,
)
from tests.data._shared_repo_helpers import (
    _fake_git_log,
    _make_minimal_project,
    _publish_project_as,
)


def test_published_meta_legacy_fallback_uses_one_git_call_for_all_dirs(tmp_path, monkeypatch):
    """Legacy dirs (no published.json) are attributed from ONE git log walk.

    Before, every such dir spawned its own `git log -1 -- <path>` on every
    /api/shared/projects request. The batched walk must still attribute
    each dir to its own author and skip a dir with no committed history.
    """
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    root = tmp_path / "evaluations"

    for project_id, author in (("proj-a", "alice"), ("proj-b", "bob"), ("proj-c", "carol")):
        _make_minimal_project(root, project_id)
        _publish_project_as(monkeypatch, url, root, project_id, author)
    for project_id in ("proj-a", "proj-b", "proj-c"):
        (shared_evaluations_root(url) / project_id / "published.json").unlink()
    (shared_evaluations_root(url) / "proj-uncommitted").mkdir()

    import quodeq.data.fs.shared_repo_meta as meta_mod
    calls: list[list[str]] = []
    real_run_git = meta_mod.run_git

    def _spy(args, **kwargs):
        calls.append(args)
        return real_run_git(args, **kwargs)

    monkeypatch.setattr(meta_mod, "run_git", _spy)
    meta = published_meta(url)

    assert {k: v["publishedBy"] for k, v in meta.items()} == {
        "proj-a": "alice", "proj-b": "bob", "proj-c": "carol",
    }
    assert all(isinstance(v["publishedAt"], int) for v in meta.values())
    assert len(calls) == 1


def test_legacy_git_attribution_chunks_pathspecs_and_merges(monkeypatch):
    """One argv with every legacy dir as a pathspec overflows the OS limit
    past a few thousand dirs, and the OSError dropped attribution for all of
    them. Pathspecs go 100 per git call; the results merge."""
    import quodeq.data.fs.shared_repo_meta as meta_mod
    calls: list[list[str]] = []
    monkeypatch.setattr(meta_mod, "run_git", _fake_git_log(calls))
    names = [f"proj-{i:03d}" for i in range(150)]

    meta = meta_mod._legacy_git_attribution(Path("/repo"), names)

    assert len(calls) == 2
    assert [len(c) - c.index("--") - 1 for c in calls] == [100, 50]
    assert set(meta) == set(names)
    assert meta["proj-000"] == {"publishedBy": "proj-000-author", "publishedAt": 1}
    assert meta["proj-149"] == {"publishedBy": "proj-149-author", "publishedAt": 50}


def test_legacy_git_attribution_failed_chunk_drops_only_its_names(monkeypatch):
    import quodeq.data.fs.shared_repo_meta as meta_mod
    calls: list[list[str]] = []
    monkeypatch.setattr(meta_mod, "run_git", _fake_git_log(calls, fail_call=2))
    names = [f"proj-{i:03d}" for i in range(150)]

    meta = meta_mod._legacy_git_attribution(Path("/repo"), names)

    assert len(calls) == 2
    assert set(meta) == set(names[:100])


def test_refresh_shared_clone_unshallows_legacy_cache(tmp_path, monkeypatch):
    """Review finding on commit 09c3dd71: unshallowing only helps NEW clones
    (ensure_shared_clone's `--depth 1` removal). A shared-clone cache
    directory created while the old `--depth 1` code was live stays shallow
    forever: ensure_shared_clone early-returns because `.git` already
    exists, and a plain `fetch origin HEAD` does not unshallow on its own
    (verified live). refresh_shared_clone must detect `.git/shallow` and run
    `git fetch --unshallow origin` first, so a legacy shallow cache
    self-heals on its next refresh instead of keeping the shallow-clone
    misattribution forever.
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
