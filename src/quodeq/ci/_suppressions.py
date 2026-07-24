"""Apply the dashboard's dismissed/deleted suppressions to CI report dicts."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys


def _coerce_line(line: object) -> int:
    try:
        return int(line)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def filter_suppressed_violations(report: dict, project_dir: Path) -> dict:
    """Return *report* with violations minus dismissed/deleted findings.

    Mirrors the dashboard's own suppression state so `ci report` and
    `export sarif` never surface a finding the user has already dismissed
    or deleted there. ``dismissed`` keys match on ``(req, file, line)``;
    ``deleted`` keys match on ``(dimension, principle, file)``.
    """
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        return report
    dim = report.get("dimension") or ""
    kept = [
        v for v in report.get("violations") or []
        if (v.get("req") or "", v.get("file") or "", _coerce_line(v.get("line"))) not in dismissed
        and (dim, v.get("practiceId") or "", v.get("file") or "") not in deleted
    ]
    return {**report, "violations": kept}
