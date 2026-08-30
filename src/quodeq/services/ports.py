"""Single boundary between the services and data layers.

Convention (documented in ARCHITECTURE.md): services import data-layer
functions from this module instead of reaching into ``quodeq.data.*``
directly, so every services -> data edge is visible in one place. The
layer checker allows any services -> data import — this is a convention,
not an enforcement point — but new or edited services code goes through
here. Contents are plain re-exports grouped by concern, plus the Protocols
services accept as injected seams. Most re-exported adapters are
dependency-light, but a few (the filesystem report parser, the
shared-results repo git plumbing) pull in a fair amount of the data layer
themselves; re-exporting them here anyway is a deliberate choice — keeping
every services -> data edge visible in one place outweighs staying thin —
not an oversight. The adapters themselves live in ``quodeq.data``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from quodeq.core.scoring.params import ScoringParams

# Per-project JSON artifacts: repository_info.json, scan.json.
from quodeq.data.fs.project_files import (  # noqa: F401
    read_repository_info,
    read_scan_total_files,
    repository_info_exists,
    write_repository_info,
)

# Per-project deleted.json suppression store (format + lock).
from quodeq.data.fs.deleted_store import (  # noqa: F401
    locked_deleted_store,
    read_deleted_entries,
    write_deleted_entries,
)

# Run-directory readers and discard-time cleanup mechanics.
from quodeq.data.fs.run_files import (  # noqa: F401
    dimension_evidence_file,
    dimension_queue_file,
    dimension_report_exists,
    evidence_file_size,
    list_dimension_evidence,
    queue_file_exists,
    read_dispatched_cache_keys,
    read_queue_files_count,
    read_queue_state,
    read_run_status_json,
    remove_matching_files,
)

# Run-artifact copy/replace mechanics (shared-repo publish staging).
from quodeq.data.fs.run_artifacts import (  # noqa: F401
    copy_file_if_exists,
    copy_matching_files,
    ensure_dir,
    replace_json_file,
)

# Agent stream files.
from quodeq.data.fs.stream_files import (  # noqa: F401
    count_active_agent_streams,
    latest_dim_activity_mtime,
)

# Legacy per-run evaluation/*.json finding details (SQL twin:
# quodeq.data.sqlite.findings_queries.read_finding_details).
from quodeq.data.fs.report_parser.finding_details import (  # noqa: F401
    read_finding_details_from_json_eval,
)

# Git clone subprocess invocation.
from quodeq.data.fs.repo_clone import clone_repo  # noqa: F401

# Per-run findings-table reads (SQL stays in the adapter) and the row-dict →
# Finding mapper that decodes what those reads return.
from quodeq.data.sqlite.findings_queries import (  # noqa: F401
    find_dismissed_matching,
    read_active_findings,
    read_finding_details,
)
from quodeq.data.sqlite._row_mappers import row_to_finding  # noqa: F401

# Custom-standard file mechanics (see StandardsStore below).
from quodeq.data.fs.standards_store import (  # noqa: F401
    compiled_exists,
    ensure_evaluators_dir,
    remove_standard,
    standard_exists,
    standard_path,
)

# Project action log (dismiss/verify events) + legacy dismissed.json fold-in.
from quodeq.data.actions_log import (  # noqa: F401
    ACTIONS_LOG_FILENAME,
    ActionLogWriter,
    read_action_events,
)
from quodeq.data.migrations.dismissed_json_to_actions_log import migrate_if_needed  # noqa: F401

# Per-project suppression_rules.json pattern store.
from quodeq.data.fs.suppression_rules import load_suppression_rules  # noqa: F401

# Run discovery + report aggregation (filesystem report parser).
from quodeq.data.fs.report_parser.runs import (  # noqa: F401
    RunInfo,
    list_runs,
    read_run_data,
    read_run_scalars,
    safe_read_dir,
)

# Repo-URL validation + child-project discovery.
from quodeq.data.fs.repo_handler import is_valid_repo_url  # noqa: F401
from quodeq.data.fs.children import find_children  # noqa: F401

# Shared-results repo: clone lifecycle, git invocation, layout + format checks.
from quodeq.data.fs.shared_repo import (  # noqa: F401
    FORMAT_NAME,
    FORMAT_VERSION,
    MARKER_FILENAME,
    PUBLISHED_META_FILENAME,
    bootstrap_repo_layout,
    check_repo_format,
    clone_lock,
    ensure_shared_clone,
    refresh_shared_clone,
    remove_clone_dir,
    run_git,
)

# Run status + dim-state file names and readers.
from quodeq.data.fs.run_status_store import (  # noqa: F401
    STATUS_FILENAME,
    UnsupportedSchemaError,
    read_status,
)
from quodeq.data.fs.dimensions_state_store import (  # noqa: F401
    FILENAME as DIMENSIONS_FILENAME,
    read_dimensions,
)

# SQL grade tables + findings projection.
from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: F401
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: F401

# Score-cache store (connection + row-level reads/writes).
from quodeq.data.sqlite.score_cache_db import (  # noqa: F401
    CACHE_WRITER_EPOCH,
    open_score_cache,
    score_cache_path_override,
)
from quodeq.data.sqlite.score_cache_store import (  # noqa: F401
    load_run_keys,
    load_run_keys_or_empty,
    read_cached_accumulated,
    read_cached_project_summary,
    read_cached_rows,
    read_project_summary_cached,
    store_run_keys,
    store_run_keys_best_effort,
    write_cached_accumulated,
    write_cached_project_summary,
    write_cached_rows,
)

# Live evidence tally (heartbeat + scan-progress counters).
from quodeq.data.fs.evidence_tally import FindingTally, tally_unique_findings  # noqa: F401

# Local git repo statistics.
from quodeq.data.fs.git_stats import count_commits_since  # noqa: F401


class GradeTablesReader(Protocol):
    """Read seam over a run's SQL grade tables (dimension/principle scores).

    The concrete implementation is ``data.sqlite.state_store.SQLiteStateStore``;
    ``services.scoring`` accepts a ``Callable[[Path], GradeTablesReader]``
    factory so the response builder can be driven by a fake without a real
    SQLite file.
    """

    def read_dimension_scores(self) -> list[dict]: ...

    def read_principle_grades(self) -> list[dict]: ...

    def read_run_score_from_dim_scores(self, params: ScoringParams | None = None) -> dict: ...


class StandardsStore(Protocol):
    """File mechanics + payload I/O seam for the standards CRUD service.

    The default implementation composes the ``standards_store`` re-exports
    above with the service's injected JSON read/write callables (built in
    ``services/standards.py``); tests can substitute an in-memory store.
    """

    def path(self, evaluators_dir: Path, standard_id: str) -> Path: ...

    def exists(self, evaluators_dir: Path, standard_id: str) -> bool: ...

    def compiled_exists(self, compiled_dir: Path, standard_id: str) -> bool: ...

    def ensure_dir(self, evaluators_dir: Path) -> None: ...

    def remove(self, evaluators_dir: Path, standard_id: str) -> None: ...

    def read(self, path: Path) -> dict: ...

    def write(self, path: Path, data: dict) -> None: ...
