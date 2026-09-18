"""Tests for published_meta attribution and index sync on published clones."""
import json
import subprocess

from quodeq.data.fs.shared_repo import (
    ensure_shared_clone,
    published_meta,
    read_state,
    remove_clone_dir,
    shared_evaluations_root,
    shared_index_db_path,
    shared_repo_path,
    sync_shared_index,
)
from tests.data._shared_repo_helpers import _make_minimal_project, _publish_project_as


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
    # remove_clone_dir, not plain rmtree: git object files are read-only,
    # which makes rmtree fail with PermissionError on Windows.
    remove_clone_dir(shared_repo_path(url))
    assert ensure_shared_clone(url) is not None

    # Simulate a legacy dir published before published.json existed: drop
    # the file from proj-a's (freshly re-cloned) working tree.
    # published_meta reads it straight off disk, not from git history, so no
    # re-commit is needed to exercise the fallback; proj-b keeps its file.
    (shared_evaluations_root(url) / "proj-a" / "published.json").unlink()

    meta = published_meta(url)
    assert meta["proj-a"]["publishedBy"] == "alice"
    assert meta["proj-b"]["publishedBy"] == "bob"
