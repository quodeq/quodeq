"""Write tools for the assistant fix worktree.

NEVER registered from build_registry(): the orchestrator registers these for
API providers only on a write-granted turn, and the MCP server registers them
only when spawned with --enable-write, which the orchestrator adds only for a
granted turn. All paths are jailed to the session WORKTREE (never the user's
working tree) via _repo_tools._jail, which prefers ctx.worktree_dir.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.assistant.tools._repo_tools import _jail
from quodeq.assistant.worktree import WorktreeError, diff_stats, diff_text

_MAX_CONTENT_CHARS = 65_536
_MAX_DIFF_CHARS = 12_000  # guard.py fences tool results at 16k; leave JSON headroom


def _jail_write(ctx: ToolContext, rel_path: str) -> Path:
    if ctx.worktree_dir is None:
        raise ToolError("write access is not enabled for this conversation")
    target = _jail(ctx, rel_path)
    workflows = (ctx.worktree_dir / ".github" / "workflows").resolve()
    if target == workflows or workflows in target.parents:
        raise ToolError("editing CI workflow files is not allowed")
    return target


def _edit_repo_file(ctx: ToolContext, path: str, old_string: str,
                    new_string: str) -> dict:
    target = _jail_write(ctx, path)
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_string) if old_string else 0
    if count == 0:
        raise ToolError("old_string not found in file")
    if count > 1:
        raise ToolError(
            f"old_string matches {count} times, add surrounding context to make it unique")
    target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
    return {"path": path, "edited": True}


def _write_repo_file(ctx: ToolContext, path: str, content: str) -> dict:
    if len(content) > _MAX_CONTENT_CHARS:
        raise ToolError(f"content exceeds {_MAX_CONTENT_CHARS} characters")
    target = _jail_write(ctx, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content.encode("utf-8"))}


def _delete_repo_file(ctx: ToolContext, path: str) -> dict:
    target = _jail_write(ctx, path)
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    target.unlink()
    return {"path": path, "deleted": True}


def _get_worktree_diff(ctx: ToolContext) -> dict:
    if ctx.worktree_dir is None:
        raise ToolError("write access is not enabled for this conversation")
    try:
        text = diff_text(ctx.worktree_dir)
        stats = diff_stats(ctx.worktree_dir)
    except WorktreeError as exc:
        raise ToolError(str(exc)) from exc
    return {"diff": text[:_MAX_DIFF_CHARS],
            "truncated": len(text) > _MAX_DIFF_CHARS, "stats": stats}


def register_write_tools(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "edit_repo_file",
        "Replace ONE unique occurrence of old_string with new_string in a file "
        "of the fix worktree. Fails if old_string is absent or ambiguous.",
        {"type": "object",
         "properties": {"path": {"type": "string"}, "old_string": {"type": "string"},
                        "new_string": {"type": "string"}},
         "required": ["path", "old_string", "new_string"]},
        lambda **kw: _edit_repo_file(ctx, **kw)))
    registry.register(ToolSpec(
        "write_repo_file",
        "Create or overwrite one file in the fix worktree.",
        {"type": "object",
         "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"]},
        lambda **kw: _write_repo_file(ctx, **kw)))
    registry.register(ToolSpec(
        "delete_repo_file",
        "Delete one file in the fix worktree.",
        {"type": "object", "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        lambda **kw: _delete_repo_file(ctx, **kw)))
    registry.register(ToolSpec(
        "get_worktree_diff",
        "Unified diff of every change made so far in the fix worktree. Call "
        "this to self-review before telling the user a fix is ready.",
        {"type": "object", "properties": {}},
        lambda **kw: _get_worktree_diff(ctx, **kw)))
