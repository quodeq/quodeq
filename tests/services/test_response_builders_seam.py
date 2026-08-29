"""_build_response_from_grade_tables is driven through injected seams.

The violation this pins ([12]/[49]): the builder used to import and construct
SQLiteStateStore and run raw SQL inline, so unit-testing it required a real
SQLite file. Now the grade reads come from a ``store_factory`` producing any
``GradeTablesReader`` and the findings read lives in the adapter
(``data.sqlite.findings_queries.read_active_findings``) — a fake drives the
whole response with no SQLite involved.
"""
from __future__ import annotations

from quodeq.services.ports import GradeTablesReader
from quodeq.services.scoring import _response_builders as rb
from quodeq.services.scoring._response_builders import _build_response_from_grade_tables

_DIM_ROWS = [
    {"dimension": "security", "score": 8.2, "grade": "B+", "exit_reason": None},
]
_P_ROWS = [
    {"dimension": "security", "principle_id": "SEC-01", "score": 9.0,
     "grade": "A", "finding_count": 1, "dismissed_count": 0},
]


class FakeGradeTables:
    def __init__(self, dim_rows=_DIM_ROWS, p_rows=_P_ROWS) -> None:
        self._dim_rows = dim_rows
        self._p_rows = p_rows

    def read_dimension_scores(self) -> list[dict]:
        return self._dim_rows

    def read_principle_grades(self) -> list[dict]:
        return self._p_rows

    def read_run_score_from_dim_scores(self, params=None) -> dict:
        return {}


def _active_row(**over) -> dict:
    base = {
        "id": 1, "practice_id": "SEC-01", "dimension": "security",
        "requirement": "SEC-01-R1", "verdict": "violation", "severity": "major",
        "file": "src/a.py", "line": 3, "end_line": 3, "title": "t",
        "reason": "r", "snippet": "s", "violation_type": "code",
        "context": "", "scope": "", "req_refs_json": None, "confidence": 90,
        "provenance_downgrade": 0, "scope_downgrade_json": None,
    }
    base.update(over)
    return base


def test_fake_reader_drives_full_response(tmp_path, monkeypatch):
    # Findings come from the adapter read; feed them in-memory so no SQLite
    # file is opened or created anywhere in this test.
    monkeypatch.setattr(rb, "read_active_findings", lambda run_dir: [
        _active_row(),
        _active_row(id=2, requirement="SEC-01-R2", verdict="compliance",
                    file="src/b.py", line=7),
    ])
    seen = []

    def factory(run_dir) -> GradeTablesReader:
        seen.append(run_dir)
        return FakeGradeTables()

    out = _build_response_from_grade_tables(tmp_path, store_factory=factory)

    assert seen == [tmp_path]
    (dim,) = out["dimensions"]
    assert dim["dimension"] == "security"
    assert dim["overallScore"] == "8.2/10"
    assert dim["overallGrade"] == "B+"
    assert dim["principles"] == [
        {"principle": "SEC-01", "score": "9.0/10", "grade": "A"}]
    assert [v["req"] for v in dim["violations"]] == ["SEC-01-R1"]
    assert [c["req"] for c in dim["compliance"]] == ["SEC-01-R2"]
    assert dim["totals"]["violationCount"] == 1
    assert dim["totals"]["complianceCount"] == 1
    assert dim["totals"]["severity"]["major"] == 1
    assert out["summary"]["dimensionsCount"] == 1
    assert not (tmp_path / "evaluation.db").exists()


def test_fake_reader_with_no_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "read_active_findings", lambda run_dir: [])

    out = _build_response_from_grade_tables(
        tmp_path, store_factory=lambda run_dir: FakeGradeTables())

    (dim,) = out["dimensions"]
    assert dim["violations"] == []
    assert dim["totals"]["violationCount"] == 0
    assert not (tmp_path / "evaluation.db").exists()
