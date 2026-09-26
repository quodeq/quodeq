"""The scalar fast path carries the counts the trend plots, without the findings.

The trend reads runs through the scalar path (grade tables only) and strips
findings before caching, so violations, majors and open requirement types
must travel as scalars or the History chart plots zeros for every run.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs.report_parser.runs import read_run_scalars
from quodeq.services.dashboard_trend import dimension_counts
from tests.api._scores_routes_helpers import _seed_run

_PROJECT = "proj"
_RUN = "r1"
_DIM = "security"


def _violation(req: str, severity: str, i: int) -> dict:
    return dict(practice_id="Confidentiality", verdict="violation", dimension=_DIM,
                file=f"f{i}.py", line=i, reason="r", req=req, severity=severity)


def test_scalars_carry_violations_majors_and_open_types(tmp_path: Path) -> None:
    violations = [_violation("S-CON-1", "minor", 0), _violation("S-CON-1", "minor", 1),
                  _violation("S-CON-2", "major", 2), _violation("S-CON-3", "critical", 3),
                  _violation("S-CON-3", "minor", 4)]
    _seed_run(tmp_path, _PROJECT, _RUN, violations)

    (dim,) = read_run_scalars(tmp_path, _PROJECT, _RUN)

    assert dim.violations == [] and dim.totals is not None
    assert (dim.totals.violation_count, dim.totals.severity.major, dim.totals.severity.critical) == (5, 1, 1)
    assert dim.open_types == 3
    assert dimension_counts(dim) == {"violations": 5, "majors": 2, "openTypes": 3}
