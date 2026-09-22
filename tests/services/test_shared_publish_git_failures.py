"""Publish failure paths against a local bare repo: rebase conflicts, stage errors, push failures, corrupt remote logs."""
import json
import os
import subprocess

import pytest

import quodeq.services.shared_publish as shared_publish
from quodeq.data.actions_log import ACTIONS_LOG_FILENAME
from quodeq.services.shared_publish import PublishError, publish_project
from quodeq.data.fs.shared_repo import ensure_shared_clone, shared_repo_path
from tests.services._shared_publish_git_fixtures import (  # noqa: F401 -- _git_identity is a pytest fixture
    _bare_origin,
    _git_identity,
    _local_project,
)


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
