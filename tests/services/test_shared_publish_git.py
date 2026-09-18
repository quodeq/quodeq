"""End-to-end publish flow against a local bare repo."""
import json
import subprocess

import pytest

import quodeq.services.shared_publish as shared_publish
from quodeq.services.shared_publish import PublishError, publish_project
from quodeq.data.fs.shared_repo import shared_repo_path
from tests.services._shared_publish_git_fixtures import (  # noqa: F401 -- _git_identity is a pytest fixture
    _bare_origin,
    _git_identity,
    _local_project,
)


def _monotonic_clock(start: float = 1_000_000.0, step: float = 50.0):
    """A stand-in for time.time() that returns a strictly increasing value on
    every call. Used instead of a finite iterator so a publish that reads the
    clock more than once (the rebase-retry path under a git race) can never
    exhaust it -- the tests that use it assert on commit count / timestamp
    ordering, both of which a monotonic clock satisfies deterministically.
    """
    state = {"t": start - step}

    def clock() -> float:
        state["t"] += step
        return state["t"]

    return clock


def test_publish_project_rejects_traversal_project_id(tmp_path, monkeypatch):
    """The service boundary validates project_id itself, not just the route."""
    (tmp_path / "evil").mkdir()  # make evaluations/../evil a real directory
    evals = tmp_path / "evaluations"
    evals.mkdir()
    monkeypatch.setattr(
        shared_publish,
        "ensure_shared_clone",
        lambda *a, **kw: pytest.fail("must not reach git with an invalid project id"),
    )
    with pytest.raises(PublishError, match="Invalid path segment"):
        publish_project("../evil", "file:///unused", evaluations_root=evals)


def test_publish_bootstraps_and_pushes(tmp_path):
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    count = publish_project("proj-uuid-1", url, evaluations_root=root)
    assert count == 1
    # verify the remote actually received the content
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", url, str(verify)], check=True, capture_output=True)
    assert (verify / "quodeq.json").exists()
    assert (verify / "evaluations" / "proj-uuid-1" / "run-1" / "status.json").exists()


def test_publish_is_idempotent_no_empty_commit(tmp_path, monkeypatch):
    """Republishing unchanged project content must never commit, regardless
    of wall-clock ticks between the two publishes. stage_project always
    rewrites published.json with a fresh publishedAt, so without the fix
    this only "passed" when both publishes happened to land in the same
    wall-clock second -- forcing distinct timestamps here makes that flake
    a deterministic failure.
    """
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    # A monotonic clock, not a finite iterator: the publish path may legitimately
    # read time.time() more than once per call (e.g. the rebase-retry loop under
    # a git push/fetch race), and this test asserts idempotency by COMMIT COUNT,
    # not by a frozen timestamp -- so a clock that keeps ticking is both correct
    # and more faithful to "regardless of wall-clock ticks between publishes".
    monkeypatch.setattr(shared_publish.time, "time", _monotonic_clock())
    publish_project("proj-uuid-1", url, evaluations_root=root)
    publish_project("proj-uuid-1", url, evaluations_root=root)  # must not raise
    repo = shared_repo_path(url)
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()
    assert len(log) == 1  # second publish added no commit


def test_publish_after_real_change_commits_and_advances_published_at(tmp_path, monkeypatch):
    """Contrast case: when project content genuinely changes between two
    publishes, a new commit IS created and published.json's publishedAt
    advances -- the idempotency fix must not suppress real updates."""
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    # Monotonic clock (see the idempotency test): every read is strictly greater
    # than the last, so the "second publishedAt > first" assertion holds no
    # matter how many times the publish path reads the clock.
    monkeypatch.setattr(shared_publish.time, "time", _monotonic_clock())

    publish_project("proj-uuid-1", url, evaluations_root=root)
    repo = shared_repo_path(url)
    meta_path = repo / "evaluations" / "proj-uuid-1" / "published.json"
    first_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # A genuinely new completed run appears locally before the second publish.
    run2 = root / "proj-uuid-1" / "run-2"
    (run2 / "evidence").mkdir(parents=True)
    (run2 / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run2 / "dimensions.json").write_text("{}")
    (run2 / "events.jsonl").write_text("{}\n")

    publish_project("proj-uuid-1", url, evaluations_root=root)

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()
    assert len(log) == 2  # real content change produced a second commit

    second_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert second_meta["publishedAt"] > first_meta["publishedAt"]


def test_publish_into_foreign_repo_refused(tmp_path):
    url = _bare_origin(tmp_path)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", url, str(seed)], check=True, capture_output=True)
    (seed / "README.md").write_text("existing project")
    for cmd in (["git", "add", "."], ["git", "commit", "-m", "x"], ["git", "push", "origin", "HEAD"]):
        subprocess.run(cmd, cwd=seed, check=True, capture_output=True)
    root = _local_project(tmp_path)
    with pytest.raises(PublishError):
        publish_project("proj-uuid-1", url, evaluations_root=root)


def test_publish_race_rebase_retry(tmp_path):
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    publish_project("proj-uuid-1", url, evaluations_root=root)
    # someone else pushes meanwhile
    other = tmp_path / "other"
    subprocess.run(["git", "clone", url, str(other)], check=True, capture_output=True)
    (other / "evaluations" / "other-proj").mkdir(parents=True)
    (other / "evaluations" / "other-proj" / "repository_info.json").write_text("{}")
    for cmd in (["git", "add", "."], ["git", "commit", "-m", "other"], ["git", "push", "origin", "HEAD"]):
        subprocess.run(cmd, cwd=other, check=True, capture_output=True)
    # our clone is now behind; a new run appears locally
    run2 = root / "proj-uuid-1" / "run-2"
    (run2 / "evidence").mkdir(parents=True)
    (run2 / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run2 / "dimensions.json").write_text("{}")
    (run2 / "events.jsonl").write_text("{}\n")
    # publish must succeed via rebase retry, and the other project must survive (additive)
    publish_project("proj-uuid-1", url, evaluations_root=root)
    verify = tmp_path / "verify2"
    subprocess.run(["git", "clone", url, str(verify)], check=True, capture_output=True)
    assert (verify / "evaluations" / "proj-uuid-1" / "run-2").exists()
    assert (verify / "evaluations" / "other-proj").exists()
