"""Rescore a single run with dismissals/deletions applied.

Reuses the same scoring engine as the original evaluation (the 4-stage
formula in ``services.rescore``). Returns the raw camelCase dict shape
that the Explorer detail endpoint expects.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.rescore import rescore_dimensions as _raw_rescore
from quodeq.services.scoring._run_scores import get_run_dimensions


def rescore_run_raw(
    reports_root: Path, project: str, run_id: str,
) -> dict:
    """Return the rescored dimensions + summary dict for a single run.

    When the project has no dismissed/deleted findings, returns the
    original dimensions and summary unchanged (just camelCased).
    """
    dimensions = get_run_dimensions(reports_root, project, run_id)
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        from quodeq.core.types import to_camel_dict
        from quodeq.data.fs.report_parser.grades import summarize_dimensions
        return {
            "dimensions": [to_camel_dict(d) for d in dimensions],
            "summary": to_camel_dict(summarize_dimensions(dimensions)),
        }
    return _raw_rescore(dimensions, dismissed, deleted)
