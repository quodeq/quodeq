"""Server-derived write-tool grant and MCP server args for one assistant turn.

Split out of orchestrator.py purely for file size. Every name below is used
from orchestrator.py (and some from tests) across that module boundary, so
none of them is underscore-private even though the module itself is;
``orchestrator.py`` imports and re-exports them for backward-compatible
imports (tests and ``api/assistant_session_routes.py`` import them from
there).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.assistant import get_provider_configs
from quodeq.assistant.adapters.cli_config import load_cli_chat_config
from quodeq.assistant.tools import ToolContext
from quodeq.assistant.worktree import ensure_session_worktree
from quodeq.config.provider import ProviderType
from quodeq.core.constants import MCP_STYLE_CONFIG_ARG, MCP_STYLE_CONFIG_FILE

if TYPE_CHECKING:
    from quodeq.assistant.orchestrator import TurnRequest
    from quodeq.data.ports.assistant import AssistantStore


@dataclass(frozen=True)
class TurnGrants:
    web_tools_on: bool
    write_on: bool
    tool_ctx: ToolContext


def provider_type(provider: str) -> str:
    return get_provider_configs().get(provider, {}).get("type", ProviderType.CLI)


# MCP config styles scoped to a single invocation: a per-turn temp config file
# (claude) or an inline config override (codex). "cli-register" is NOT here:
# it mutates a global settings file, so concurrent sessions could interleave
# and a no-grant turn would spawn its MCP server against a grant turn's
# registration, leaking write tools jailed to another session's worktree.
ISOLATED_MCP_STYLES = frozenset({MCP_STYLE_CONFIG_FILE, MCP_STYLE_CONFIG_ARG})


def write_safe_provider(provider: str) -> bool:
    """Whether the write grant may activate for this provider. API providers
    register tools in-process (no MCP config involved); CLI providers qualify
    only when their MCP config is per-invocation isolated."""
    if provider_type(provider) != ProviderType.CLI:
        return True
    try:
        return load_cli_chat_config(provider).mcp_style in ISOLATED_MCP_STYLES
    except KeyError:
        return False


def mcp_server_args(request: "TurnRequest", tool_ctx: ToolContext) -> list[str]:
    args = [
        "--db-path", str(tool_ctx.repository.db_path),
        "--session-id", request.session_id,
        "--evaluators-dir", str(tool_ctx.evaluators_dir),
        "--compiled-dir", str(tool_ctx.compiled_dir),
        "--dimensions-file", str(tool_ctx.dimensions_file),
    ]
    if tool_ctx.run_dir is not None:
        args += ["--run-dir", str(tool_ctx.run_dir)]
    if tool_ctx.repo_root is not None:
        args += ["--repo-root", str(tool_ctx.repo_root)]
    if tool_ctx.project_id is not None:
        args += ["--project-id", str(tool_ctx.project_id)]
    if tool_ctx.reports_dir is not None:
        args += ["--reports-dir", str(tool_ctx.reports_dir)]
    if tool_ctx.worktree_dir is not None:
        args += ["--enable-write", "--worktree-dir", str(tool_ctx.worktree_dir)]
    if tool_ctx.read_only:
        args += ["--read-only"]
    if tool_ctx.score_cache_path is not None:
        args += ["--score-cache-override", str(tool_ctx.score_cache_path)]
    return args


def attached_git_repo(tool_ctx: ToolContext) -> bool:
    """True when the session has a local git checkout, resolved by the composition root."""
    return tool_ctx.repo_is_git


def _write_is_grantable(request: "TurnRequest", tool_ctx: ToolContext) -> bool:
    """True when every server-side condition for write access holds: not
    read-only, a local git repo attached, and a write-safe provider (the
    client's write_enabled flag alone is never sufficient)."""
    return bool(request.write_enabled and not tool_ctx.read_only
                and attached_git_repo(tool_ctx) and write_safe_provider(request.provider))


def write_available(repo_root: str | None, provider: str, read_only: bool) -> bool:
    """Whether the write-tool grant could ever activate for a new session:
    not read-only, a local git repo attached, write-safe provider."""
    return bool(not read_only and repo_root and (Path(repo_root) / ".git").exists()
                and write_safe_provider(provider))


def resolve_write_grant(request: "TurnRequest", repository: "AssistantStore",
                         tool_ctx: ToolContext, web_tools_on: bool) -> TurnGrants:
    """Server-derived write grant, mirror of web_tools_on: the client flag
    alone is never enough. Requires an attached LOCAL git repo and a
    provider whose tool wiring is per-invocation isolated. When granted,
    ensures the session worktree exists and points tool_ctx at it. Returns
    a TurnGrants bundling that tool_ctx, write_on, and the caller-supplied
    web_tools_on."""
    write_on = _write_is_grantable(request, tool_ctx)
    if write_on:
        manager = ensure_session_worktree(
            repository, repo_root=tool_ctx.repo_root,
            project_id=tool_ctx.project_id, session_id=request.session_id)
        tool_ctx = replace(tool_ctx, worktree_dir=manager.path)
    return TurnGrants(web_tools_on=web_tools_on, write_on=write_on, tool_ctx=tool_ctx)
