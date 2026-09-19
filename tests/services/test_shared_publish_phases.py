"""Unit tests for the two phase helpers behind ``publish_project``.

``_prepare_workspace`` is a context manager: it validates the project id,
takes the process-wide clone lock and yields (project_dir, repo) with the
lock still held. ``_commit_and_push`` stages, commits and pushes.
"""
import subprocess

import pytest

from quodeq.services.shared_publish import (
    PublishError,
    _commit_and_push,
    _prepare_workspace,
)
from tests.services._shared_publish_git_fixtures import (  # noqa: F401 -- _git_identity is a pytest fixture
    _bare_origin,
    _git_identity,
    _local_project,
)


class TestPrepareWorkspace:
    def test_rejects_a_traversing_project_id(self, tmp_path):
        url = _bare_origin(tmp_path)
        root = _local_project(tmp_path)

        with pytest.raises(PublishError):
            with _prepare_workspace("../escape", url, root, None):
                pass

    def test_rejects_an_unknown_project(self, tmp_path):
        url = _bare_origin(tmp_path)
        root = _local_project(tmp_path)

        with pytest.raises(PublishError, match="not found in local evaluations"):
            with _prepare_workspace("proj-uuid-missing", url, root, None):
                pass

    def test_yields_the_project_dir_and_a_bootstrapped_clone(self, tmp_path):
        url = _bare_origin(tmp_path)
        root = _local_project(tmp_path)

        with _prepare_workspace("proj-uuid-1", url, root, None) as (project_dir, repo):
            assert project_dir == root / "proj-uuid-1"
            assert (repo / ".git").is_dir()
            # An empty origin is bootstrapped before the body runs.
            assert (repo / "evaluations").is_dir()

    def test_holds_the_clone_lock_for_the_body(self, tmp_path):
        """The lock is an RLock held across the whole yielded body, so a
        re-entrant acquire on this thread must succeed while inside."""
        from quodeq.services.shared_publish import clone_lock

        url = _bare_origin(tmp_path)
        root = _local_project(tmp_path)

        with _prepare_workspace("proj-uuid-1", url, root, None):
            with clone_lock(url, None):
                pass


class TestCommitAndPush:
    def test_stages_commits_and_pushes_the_project(self, tmp_path):
        url = _bare_origin(tmp_path)
        root = _local_project(tmp_path)

        with _prepare_workspace("proj-uuid-1", url, root, None) as (project_dir, repo):
            from quodeq.services.shared_publish import stage_project
            count = stage_project(project_dir, repo / "evaluations" / "proj-uuid-1")
            _commit_and_push(repo, "proj-uuid-1", count)

        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=url.removeprefix("file://"), check=True, capture_output=True, text=True,
        ).stdout
        assert "evaluations/proj-uuid-1/repository_info.json" in listing

    def test_raises_publish_error_when_git_add_fails(self, tmp_path, monkeypatch):
        import quodeq.services.shared_publish as shared_publish

        url = _bare_origin(tmp_path)
        root = _local_project(tmp_path)

        with _prepare_workspace("proj-uuid-1", url, root, None) as (_project_dir, repo):
            monkeypatch.setattr(
                shared_publish, "run_git", lambda *a, **kw: (False, "fatal: pathspec"),
            )
            with pytest.raises(PublishError, match="git add failed"):
                _commit_and_push(repo, "proj-uuid-1", 0)
