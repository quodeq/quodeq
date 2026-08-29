"""Use case behind ``GET /api/rescore``: rescore one run of one project.

Owns everything the route used to inline — parameter validation, project
directory resolution, "latest run" selection, dismissed/deleted/suppression
loading, and the :func:`~quodeq.services.rescore.rescore_dimensions` call —
so the "which run counts as latest" rule is a plain function, testable
without Flask. The route keeps only query parsing and HTTP status mapping.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from quodeq.services.deleted import deleted_keys as load_deleted_keys
from quodeq.services.dismissed import dismissed_keys as load_dismissed_keys
from quodeq.services.rescore import rescore_dimensions
from quodeq.services.run_reports import list_runs, read_run_data
from quodeq.services.suppression import load_suppression_rules
from quodeq.shared.validation import resolve_child_dir, validate_path_segment

RescoreStatus = Literal["ok", "invalid_param", "project_not_found", "run_not_found"]


@dataclass(frozen=True)
class RescoreOutcome:
    """Plain result of :func:`rescore_project_run`.

    ``status`` carries the distinctions the route maps to HTTP statuses:

    - ``"ok"``: *result* holds the rescored payload (dimensions + summary).
    - ``"invalid_param"``: project or run failed path-segment validation.
    - ``"project_not_found"``: the project directory does not exist, or it
      has no runs to resolve ``latest`` against.
    - ``"run_not_found"``: the project exists but the requested run (or its
      data) does not.
    """

    status: RescoreStatus
    result: dict[str, Any] | None = None


def resolve_latest_run_id(reports_root: Path, project: str) -> str | None:
    """Return the id of *project*'s newest run, or None when it has none.

    "Latest" is the first entry of :func:`list_runs`, which sorts runs
    newest-first by date.
    """
    runs = list_runs(reports_root, project, limit=1)
    return runs[0].run_id if runs else None


def rescore_project_run(reports_root: Path, project: str, run_id: str) -> RescoreOutcome:
    """Rescore *project*'s *run_id* after dismissals/deletions/suppressions.

    *run_id* may be empty or ``"latest"``, both meaning the newest run.
    """
    try:
        validate_path_segment(project)
        if run_id and run_id != "latest":
            validate_path_segment(run_id)
    except ValueError:
        return RescoreOutcome("invalid_param")

    # Resolve by listing rather than joining: *project* is compared against
    # real entries and never concatenated onto *reports_root*, so a hostile
    # value matches nothing instead of needing containment afterwards.
    # A miss here is "no such project", which is a 404 like any other.
    resolved_dir = resolve_child_dir(reports_root, project)
    if resolved_dir is None:
        return RescoreOutcome("project_not_found")
    project_dir = Path(resolved_dir)
    project = project_dir.name

    # Resolve run ID
    if not run_id or run_id == "latest":
        latest = resolve_latest_run_id(reports_root, project)
        if latest is None:
            return RescoreOutcome("project_not_found")
        run_id = latest

    resolved_run_dir = resolve_child_dir(project_dir, run_id)
    if resolved_run_dir is None:
        return RescoreOutcome("run_not_found")

    try:
        dimensions = read_run_data(reports_root, project, run_id)
    except FileNotFoundError:
        return RescoreOutcome("run_not_found")

    dismissed = load_dismissed_keys(project_dir)
    deleted = load_deleted_keys(project_dir)

    # *dimensions* were read from this one run, so its directory is the
    # evidence basis for the rescore.
    result = rescore_dimensions(
        dimensions, dismissed, deleted, run_dir=Path(resolved_run_dir),
        rules=load_suppression_rules(project_dir))
    return RescoreOutcome("ok", result)
