"""Single boundary between the services and data layers.

Convention (documented in ARCHITECTURE.md): services import data-layer
functions from this module instead of reaching into ``quodeq.data.*``
directly, so every services -> data edge is visible in one place. The
layer checker allows any services -> data import — this is a convention,
not an enforcement point — but new or edited services code goes through
here. Contents are dependency-light on purpose: plain re-exports grouped
by concern, plus the Protocols services accept as injected seams. The
adapters themselves live in ``quodeq.data``.
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
    dimension_queue_file,
    list_dimension_evidence,
    queue_file_exists,
    read_dispatched_cache_keys,
    read_queue_files_count,
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
from quodeq.data.fs.stream_files import count_active_agent_streams  # noqa: F401

# Legacy per-run evaluation/*.json finding details (SQL twin:
# quodeq.data.sqlite.findings_queries.read_finding_details).
from quodeq.data.fs.report_parser.finding_details import (  # noqa: F401
    read_finding_details_from_json_eval,
)

# Git clone subprocess invocation.
from quodeq.data.fs.repo_clone import clone_repo  # noqa: F401

# Per-run findings-table reads (SQL stays in the adapter) and the row-dict →
# Finding mapper that decodes what those reads return.
from quodeq.data.sqlite.findings_queries import read_active_findings  # noqa: F401
from quodeq.data.sqlite._row_mappers import row_to_finding  # noqa: F401

# Custom-standard file mechanics (see StandardsStore below).
from quodeq.data.fs.standards_store import (  # noqa: F401
    compiled_exists,
    ensure_evaluators_dir,
    remove_standard,
    standard_exists,
    standard_path,
)


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
