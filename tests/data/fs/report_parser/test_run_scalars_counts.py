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
    assert dimension_counts(dim) == {"violations": 5, "majors": 2, "openTypes": 3, "critical": 1}


def _compliance(req: str, i: int) -> dict:
    return dict(practice_id="Confidentiality", verdict="compliance", dimension=_DIM,
                file=f"c{i}.py", line=i, reason="ok", req=req, severity="minor")


def test_scalars_carry_the_compliance_count(tmp_path: Path) -> None:
    rows = [_violation("S-CON-1", "minor", 0), _violation("S-CON-2", "major", 1),
            _compliance("S-CON-1", 2), _compliance("S-CON-3", 3), _compliance("S-CON-3", 4)]
    _seed_run(tmp_path, _PROJECT, _RUN, rows)

    (dim,) = read_run_scalars(tmp_path, _PROJECT, _RUN)

    assert dim.totals is not None
    assert (dim.totals.violation_count, dim.totals.compliance_count) == (2, 3)


def _scorable() -> list[dict]:
    """Enough violations in one principle to clear the confidence floor, so the run has a score."""
    return [_violation(f"S-CON-{i}", "minor", i) for i in range(5)]


def test_scalars_carry_the_stored_files_read(tmp_path: Path) -> None:
    import sqlite3

    run_dir = _seed_run(tmp_path, _PROJECT, _RUN, _scorable())
    with sqlite3.connect(run_dir / "evaluation.db") as conn:
        conn.execute("UPDATE dimension_scores SET files_read = 584, source_count = 1494")

    (dim,) = read_run_scalars(tmp_path, _PROJECT, _RUN)

    assert dim.files_read == 584


def test_scalars_keep_a_zero_files_read(tmp_path: Path) -> None:
    """A coverage-0 stub must stay 0 (not None): has_valid_score rejects 0 and trusts None."""
    import sqlite3

    run_dir = _seed_run(tmp_path, _PROJECT, _RUN, _scorable())
    with sqlite3.connect(run_dir / "evaluation.db") as conn:
        conn.execute("UPDATE dimension_scores SET files_read = 0, source_count = 0")

    (dim,) = read_run_scalars(tmp_path, _PROJECT, _RUN)

    assert dim.files_read == 0


def test_scalars_carry_the_exit_reason_and_the_manifest_metadata(tmp_path: Path) -> None:
    """What a full read attaches from the grade row and the run manifest, the scalar read attaches too."""
    import json
    import sqlite3

    run_dir = _seed_run(tmp_path, _PROJECT, _RUN, _scorable())
    with sqlite3.connect(run_dir / "evaluation.db") as conn:
        conn.execute("UPDATE dimension_scores SET exit_reason = 'failure_streak'")
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "manifest.json").write_text(
        json.dumps({"source_files_count": 1494, "language": "python"}), encoding="utf-8")

    (dim,) = read_run_scalars(tmp_path, _PROJECT, _RUN)

    assert (dim.exit_reason, dim.source_file_count, dim.discipline) == ("failure_streak", 1494, "python")


def test_scalars_leave_the_manifest_metadata_unset_without_a_manifest(tmp_path: Path) -> None:
    _seed_run(tmp_path, _PROJECT, _RUN, _scorable())

    (dim,) = read_run_scalars(tmp_path, _PROJECT, _RUN)

    assert (dim.exit_reason, dim.source_file_count, dim.discipline) == (None, None, None)
