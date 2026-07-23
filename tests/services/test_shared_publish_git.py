"""End-to-end publish flow against a local bare repo."""
import json
import os
import subprocess
from pathlib import Path

import pytest

import quodeq.services.shared_publish as shared_publish
from quodeq.data.actions_log import ACTIONS_LOG_FILENAME
from quodeq.services.shared_publish import PublishError, publish_project
from quodeq.services.shared_repo import ensure_shared_clone, shared_repo_path


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


def _bare_origin(tmp_path: Path) -> str:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


def _local_project(tmp_path: Path) -> Path:
    root = tmp_path / "evaluations"
    project = root / "proj-uuid-1"
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")
    (run / "evidence" / "manifest.json").write_text("{}")
    return root


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")


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


def test_failed_rebase_conflict_is_aborted_and_clone_recovers(tmp_path, monkeypatch):
    """A real rebase conflict must not wedge the persistent clone.

    The clone under QUODEQ_CACHE_ROOT is reused across publishes, so a
    failed rebase that leaves .git/rebase-merge on disk breaks every
    subsequent publish with git's "already a rebase-merge directory"
    error instead of a clean PublishError.
    """
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    publish_project("proj-uuid-1", url, evaluations_root=root)

    # A change we will try to publish next, conflicting with a racing push.
    (root / "proj-uuid-1" / "repository_info.json").write_text('{"name":"local-change"}')

    other_counter = {"n": 0}

    def push_conflicting_change() -> None:
        # Real git operations from a second clone, racing our own publish:
        # it modifies the SAME file our pending commit touches, so the
        # rebase that follows a rejected push hits a genuine conflict.
        other_counter["n"] += 1
        other = tmp_path / f"other-{other_counter['n']}"
        subprocess.run(["git", "clone", url, str(other)], check=True, capture_output=True)
        (other / "evaluations" / "proj-uuid-1" / "repository_info.json").write_text(
            json.dumps({"name": f"remote-change-{other_counter['n']}"})
        )
        for cmd in (
            ["git", "add", "."],
            ["git", "commit", "-m", f"remote edit {other_counter['n']}"],
            ["git", "push", "origin", "HEAD"],
        ):
            subprocess.run(cmd, cwd=other, check=True, capture_output=True)

    real_run_git = shared_publish.run_git

    def racing_run_git(args, *, cwd=None, timeout=300):
        # Only the plain "push origin HEAD" attempt races; explicit-refspec
        # pushes and everything else go straight to the real implementation.
        if args == ["push", "origin", "HEAD"]:
            push_conflicting_change()
        return real_run_git(args, cwd=cwd, timeout=timeout)

    monkeypatch.setattr(shared_publish, "run_git", racing_run_git)

    repo = shared_repo_path(url)

    with pytest.raises(PublishError) as excinfo_2:
        publish_project("proj-uuid-1", url, evaluations_root=root)
    assert not (repo / ".git" / "rebase-merge").exists()

    # Without the fix, the clone above would still carry a wedged
    # .git/rebase-merge, and this next call would fail with git's own
    # "already a rebase-merge directory" error rather than a clean,
    # push-rejected PublishError.
    with pytest.raises(PublishError) as excinfo_3:
        publish_project("proj-uuid-1", url, evaluations_root=root)
    assert not (repo / ".git" / "rebase-merge").exists()
    assert "already a rebase-merge directory" not in str(excinfo_3.value)
    assert "already a rebase-merge directory" not in str(excinfo_2.value)


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod-based permission denial is ineffective as root or on Windows",
)
def test_stage_failure_raises_publish_error_not_oserror(tmp_path):
    """An OSError from bootstrap/stage (disk full, permissions) must
    surface as PublishError, matching the documented "raises PublishError
    on any failure" contract, not leak as a raw OSError.
    """
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)

    # Pre-create the persistent clone (same call publish_project would
    # make), then make its directory unwritable so bootstrap_repo_layout's
    # write_text calls fail with a real PermissionError.
    repo = ensure_shared_clone(url, None)
    assert repo is not None
    repo.chmod(0o555)
    try:
        with pytest.raises(PublishError) as excinfo:
            publish_project("proj-uuid-1", url, evaluations_root=root)
        assert "failed to stage project files" in str(excinfo.value)
    finally:
        repo.chmod(0o755)


def test_retry_after_push_failure_still_reaches_remote(tmp_path, monkeypatch):
    """A publish whose commit succeeds but whose push fails must not report
    success on the next retry without actually pushing.

    The second call re-stages identical project files, so `git diff --cached
    --quiet` comes back clean (nothing NEW to stage) even though the first
    call's commit is still sitting unpushed in the local clone. The old code
    read that clean diff as "nothing to publish" and returned success
    without ever attempting a push, so the remote never received the data.
    """
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)

    real_run_git = shared_publish.run_git

    def failing_push(args, *, cwd=None, timeout=300):
        # Fail every push attempt: both the plain "push origin HEAD" and
        # the explicit-refspec fallback start with ["push", "origin", ...].
        if args[:2] == ["push", "origin"]:
            return False, "simulated network error"
        return real_run_git(args, cwd=cwd, timeout=timeout)

    monkeypatch.setattr(shared_publish, "run_git", failing_push)

    with pytest.raises(PublishError):
        publish_project("proj-uuid-1", url, evaluations_root=root)

    # Restore the healthy git wrapper for the retry.
    monkeypatch.setattr(shared_publish, "run_git", real_run_git)

    count = publish_project("proj-uuid-1", url, evaluations_root=root)
    assert count == 1

    # The regression: without the fix, this second call would return
    # success while the remote still has none of the project's data.
    verify = tmp_path / "verify-retry"
    subprocess.run(["git", "clone", url, str(verify)], check=True, capture_output=True)
    assert (verify / "quodeq.json").exists()
    assert (verify / "evaluations" / "proj-uuid-1" / "run-1" / "status.json").exists()


def test_non_utf8_remote_actions_log_raises_publish_error_not_unicode_error(tmp_path):
    """merge_actions_log reads the remote's actions.jsonl via Path.read_text
    (encoding='utf-8'). A non-UTF8 remote file raises UnicodeDecodeError,
    a ValueError, which must surface through the documented PublishError
    contract rather than leak out of publish_project as a raw exception.
    """
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    publish_project("proj-uuid-1", url, evaluations_root=root)

    # Push a genuinely corrupted actions.jsonl to the remote from a second
    # clone. publish_project's own refresh_shared_clone does `git reset
    # --hard FETCH_HEAD`, which would wipe an uncommitted edit made
    # directly in the persistent clone before staging ever ran, so the
    # corruption has to actually be committed and pushed to survive that.
    other = tmp_path / "other-corrupt"
    subprocess.run(["git", "clone", url, str(other)], check=True, capture_output=True)
    (other / "evaluations" / "proj-uuid-1" / ACTIONS_LOG_FILENAME).write_bytes(
        b"\xff\xfe not valid utf-8\n"
    )
    for cmd in (
        ["git", "add", "."],
        ["git", "commit", "-m", "corrupt actions log"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=other, check=True, capture_output=True)

    # A local actions.jsonl must also exist so merge_actions_log actually
    # reaches the read of the (now corrupted) remote copy in the same
    # code path a real merge takes.
    (root / "proj-uuid-1" / ACTIONS_LOG_FILENAME).write_text(
        json.dumps({"timestamp": "1", "type": "note"}) + "\n", encoding="utf-8"
    )

    with pytest.raises(PublishError) as excinfo:
        publish_project("proj-uuid-1", url, evaluations_root=root)
    assert "failed to stage project files" in str(excinfo.value)


def test_push_falls_back_to_explicit_refspec_when_origin_head_push_fails(tmp_path, monkeypatch):
    """_push falls back to an explicit refspec push when a plain
    ``push origin HEAD`` fails. The empty-remote condition this fallback
    targets cannot be reproduced deterministically with this git version,
    so the first push call is forced to fail; everything else runs for
    real.
    """
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)

    real_run_git = shared_publish.run_git
    state = {"failed_once": False}

    def flaky_first_push(args, *, cwd=None, timeout=300):
        if not state["failed_once"] and args == ["push", "origin", "HEAD"]:
            state["failed_once"] = True
            return False, "simulated"
        return real_run_git(args, cwd=cwd, timeout=timeout)

    monkeypatch.setattr(shared_publish, "run_git", flaky_first_push)

    count = publish_project("proj-uuid-1", url, evaluations_root=root)
    assert count == 1
    assert state["failed_once"]  # the fallback branch was actually exercised

    verify = tmp_path / "verify-fallback"
    subprocess.run(["git", "clone", url, str(verify)], check=True, capture_output=True)
    assert (verify / "quodeq.json").exists()
    assert (verify / "evaluations" / "proj-uuid-1" / "run-1" / "status.json").exists()
