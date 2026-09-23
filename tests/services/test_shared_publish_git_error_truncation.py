"""git add/commit/push failures all truncate the raw git output to the same
length before embedding it in a PublishError message. The commit/push
truncation lives in _publish_git.py, which cannot import GIT_ERROR_SNIPPET_MAX_CHARS
at module level (circular import with shared_publish.py -- see that module's
docstring), so it imports the constant in-function from shared_publish.py,
the same way it already does for PublishError."""
from __future__ import annotations

import quodeq.services.shared_publish as shared_publish
from quodeq.services._publish_git import commit_staged_changes, push_with_rebase_fallback
from quodeq.services.shared_publish import GIT_ERROR_SNIPPET_MAX_CHARS, PublishError


def test_git_error_snippet_length_is_300():
    assert GIT_ERROR_SNIPPET_MAX_CHARS == 300


def test_commit_failure_message_truncated_to_the_shared_length(tmp_path, monkeypatch):
    long_output = "x" * (GIT_ERROR_SNIPPET_MAX_CHARS + 50)

    def fake_run_git(args, *, cwd=None, timeout=300):
        if args[:2] == ["diff", "--cached"] and "--name-only" in args:
            return True, ""
        if args == ["diff", "--cached", "--quiet"]:
            return False, ""  # "not nothing_staged" -> proceed to commit
        if args[:1] == ["commit"]:
            return False, long_output
        return True, ""

    monkeypatch.setattr(shared_publish, "run_git", fake_run_git)

    try:
        commit_staged_changes(tmp_path, "proj", 1)
        raise AssertionError("expected PublishError")
    except PublishError as exc:
        embedded = str(exc).rsplit(", ", 1)[-1]
        assert len(embedded) == GIT_ERROR_SNIPPET_MAX_CHARS


def test_push_failure_message_truncated_to_the_shared_length(tmp_path, monkeypatch):
    long_output = "y" * (GIT_ERROR_SNIPPET_MAX_CHARS + 50)

    def fake_run_git(args, *, cwd=None, timeout=300):
        return False, long_output

    monkeypatch.setattr(shared_publish, "run_git", fake_run_git)

    try:
        push_with_rebase_fallback(tmp_path)
        raise AssertionError("expected PublishError")
    except PublishError as exc:
        embedded = str(exc).rsplit(". ", 1)[-1]
        assert len(embedded) == GIT_ERROR_SNIPPET_MAX_CHARS
