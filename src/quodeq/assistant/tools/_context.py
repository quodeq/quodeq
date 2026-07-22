"""Shared per-session context handed to every tool handler."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.data.sqlite.assistant_repository import AssistantRepository


@dataclass(frozen=True)
class ToolContext:
    repository: AssistantRepository
    session_id: str
    run_dir: Path | None
    repo_root: Path | None
    evaluators_dir: Path
    compiled_dir: Path
    dimensions_file: Path
    # Accumulated/overview scope: the evaluations-dir project name and the
    # evaluations root. Both optional so run-scoped-only sessions still work.
    project_id: str | None = None
    reports_dir: Path | None = None
    # Set only for write-granted turns: the session's fix worktree. When set,
    # repo reads AND writes are jailed here so the model sees its own edits.
    worktree_dir: Path | None = None
    # Read-only (shared/remote) session: mutating tools are never registered
    # and the write grant can never activate. reports_dir/run_dir point at
    # the shared clone.
    read_only: bool = False
    # When set, any code path that DISPATCHES tools must wrap execution in
    # score_cache_path_override(score_cache_path) so rescoring hits the
    # per-clone cache DB, never the local one (the routes_shared
    # _with_shared_root mechanism). Wrapped in the messages-route worker and
    # the MCP server main.
    score_cache_path: Path | None = None
