"""``attached_git_repo`` reads ``ToolContext.repo_is_git`` (row 9198).

The turn orchestrator used to probe the filesystem itself
(``(tool_ctx.repo_root / ".git").exists()``) -- an io-in-orchestration
violation. The composition roots (``api/_assistant_helpers.build_tool_context``,
the assistant MCP server's ``_build_registry_from_args``) now resolve that
once when building the ``ToolContext``, and the orchestrator just reads the
field. These tests pin that the orchestrator no longer looks at the
filesystem at all: a real ``.git`` dir on disk is irrelevant when the field
says otherwise, and vice versa.
"""
from __future__ import annotations

from quodeq.assistant import orchestrator
from quodeq.assistant.tools import ToolContext


def _ctx(tmp_path, **overrides) -> ToolContext:
    kwargs = dict(
        repository=None, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )
    kwargs.update(overrides)
    return ToolContext(**kwargs)


def test_defaults_to_false_with_no_repo_root(tmp_path):
    assert orchestrator.attached_git_repo(_ctx(tmp_path)) is False


def test_true_when_field_is_set_even_without_a_real_git_dir(tmp_path):
    """A composition root can set repo_is_git True; the orchestrator must
    trust it rather than re-checking the filesystem."""
    repo_root = tmp_path / "repo-no-git-dir"
    repo_root.mkdir()
    ctx = _ctx(tmp_path, repo_root=repo_root, repo_is_git=True)
    assert orchestrator.attached_git_repo(ctx) is True


def test_false_when_field_is_unset_even_with_a_real_git_dir_on_disk(tmp_path):
    """A real .git directory on disk must NOT make this True on its own --
    only the composition-root-resolved field does. Pins that the
    orchestrator performs no filesystem probe of its own."""
    repo_root = tmp_path / "repo-with-git-dir"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    ctx = _ctx(tmp_path, repo_root=repo_root, repo_is_git=False)
    assert orchestrator.attached_git_repo(ctx) is False
