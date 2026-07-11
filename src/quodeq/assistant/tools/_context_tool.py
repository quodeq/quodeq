"""Session-scope discovery tool for assistant agents."""
from __future__ import annotations

from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolRegistry, ToolSpec


def _run_id(ctx: ToolContext) -> str | None:
    if ctx.run_dir is None:
        return None
    return ctx.run_dir.name


def _guidance(ctx: ToolContext) -> str:
    run_attached = ctx.run_dir is not None and ctx.run_dir.exists()
    repo_attached = ctx.repo_root is not None and ctx.repo_root.exists()
    overview_available = ctx.project_id is not None and ctx.reports_dir is not None
    if run_attached and repo_attached:
        return "Use get_scores/get_violations for the selected run and read_repo_file for source context."
    if run_attached:
        return "Use get_scores/get_violations for the selected run; source repository files are not attached."
    if overview_available and repo_attached:
        return "Use get_overview/get_violations for the project overview and read_repo_file for source context."
    if overview_available:
        return "Use get_overview/get_violations for the project overview; source repository files are not attached."
    if repo_attached:
        return "Only repository source files are attached; use read_repo_file/list_repo_dir."
    return "No project or run is attached; ask the user to open a project overview or run."


def _get_context(ctx: ToolContext) -> dict:
    run_attached = ctx.run_dir is not None and ctx.run_dir.exists()
    repo_attached = ctx.repo_root is not None and ctx.repo_root.exists()
    overview_available = ctx.project_id is not None and ctx.reports_dir is not None
    return {
        "projectId": ctx.project_id,
        "runId": _run_id(ctx),
        "runSelected": ctx.run_dir is not None,
        "runDirAttached": run_attached,
        "repoAttached": repo_attached,
        "overviewAvailable": overview_available,
        "guidance": _guidance(ctx),
    }


def register_context_tool(registry: ToolRegistry, ctx: ToolContext) -> None:
    registry.register(ToolSpec(
        "get_context",
        "Return the active Quodeq assistant scope: project, selected run, "
        "repository attachment, overview availability, and which tools to use next. "
        "Call this first when the session scope is unclear.",
        {"type": "object", "properties": {}},
        lambda **kw: _get_context(ctx),
    ))
