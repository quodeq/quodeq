"""Shared per-session context handed to every tool handler."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from quodeq.data.ports.assistant import AssistantStore
from quodeq.data.ports.findings import FindingsRepository


@dataclass(frozen=True)
class ToolContext:
    repository: AssistantStore
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
    # Per-project visible-standards selection
    # (<repo>/.quodeq/standards-visibility.json, see
    # core.standards.visibility). General-purpose read tools filter to this set
    # so the assistant never quotes dimensions the dashboard hides. Production
    # always resolves a concrete selection (load_visible_standard_ids falls
    # back to DEFAULT_VISIBLE_STANDARDS even with no repo root); None is the
    # explicit "no filtering" opt-out, kept for any future caller that wants
    # it, not something production code paths produce.
    visible_standard_ids: tuple[str, ...] | None = None
    # Builds the per-run findings reader for the read tools. Composition
    # roots (api/_assistant_helpers.build_tool_context, the MCP server) pass
    # the concrete SQLite factory; tests can inject a fake. None falls back
    # to the SQLite default inside the tools module so directly-constructed
    # contexts keep working.
    findings_repo_factory: Callable[[Path], FindingsRepository] | None = None
