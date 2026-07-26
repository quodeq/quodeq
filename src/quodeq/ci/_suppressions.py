"""Apply the dashboard's dismissed/deleted suppressions to CI report dicts."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.suppression import is_deleted, is_dismissed


def filter_suppressed_violations(report: dict, project_dir: Path) -> dict:
    """Return *report* with violations minus dismissed/deleted findings.

    Mirrors the dashboard's own suppression state so `ci report` and
    `export sarif` never surface a finding the user has already dismissed
    or deleted there. ``dismissed`` keys match on ``(req, file, line)``;
    ``deleted`` keys match on ``(dimension, principle, file)``.

    The dimension used for the deleted-key match is taken per-violation
    (``v["dimension"]``) when present, falling back to the report-level
    ``report["dimension"]``. Per-dimension scored reports (`security.json`
    etc.) only carry the report-level field, so the fallback is what
    applies there. Evidence-derived reports (`ci report --from-evidence`,
    `quodeq review`) wrap several real dimensions under one synthetic
    ``"pr-diff"`` report, with each violation carrying its own real
    ``dimension`` — using the report-level value there would compare
    ``"pr-diff"`` against a real dimension and never match.
    """
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        return report
    report_dim = report.get("dimension") or ""

    def _keep(v: dict) -> bool:
        # Scored report JSON names the field "principle"; evidence-derived
        # reports (--from-evidence, quodeq review) carry "practiceId".
        principle = v.get("principle") or v.get("practiceId")
        return not is_dismissed(dismissed, req=v.get("req"), principle=principle,
                                file=v.get("file"), line=v.get("line")) \
            and not is_deleted(deleted, dimension=v.get("dimension") or report_dim,
                               principle=principle, file=v.get("file"))

    return {**report, "violations": [v for v in report.get("violations") or [] if _keep(v)]}
