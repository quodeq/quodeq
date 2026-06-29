"""parse_eval_from_json drops principles that are not in the dimension's
standard, so a stale per-dimension JSON carrying a phantom "N/A" principle no
longer renders as an extra dashboard card / radial vertex.

Read-time guard: this also fixes already-written runs, since the dashboard
re-parses the frozen evaluation/<dim>.json on every view.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.report_parser._eval_parsing import parse_eval_from_json


def _write_compiled_standard(
    compiled_dir: Path, dimension: str, principle_names: list[str],
) -> None:
    compiled_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": dimension,
        "name": dimension,
        "principles": [
            {"name": name, "requirements": [{"id": f"{name[:3].upper()}-1"}]}
            for name in principle_names
        ],
    }
    (compiled_dir / f"{dimension}.json").write_text(json.dumps(data), encoding="utf-8")


def _write_eval(json_path: Path) -> None:
    json_path.write_text(json.dumps({
        "dimension": "maintainability",
        "overallScore": "6.7/10",
        "overallGrade": "Adequate",
        "principles": [
            {"name": "Modularity", "score": "5.2/10", "grade": "Adequate"},
            {"name": "Testability", "score": "8.7/10", "grade": "Good"},
            {"name": "N/A", "score": None, "grade": "Insufficient"},
        ],
        "violations": [
            {"principle": "Modularity", "file": "b.py", "line": 1,
             "title": "x", "reason": "", "severity": "minor"},
            {"principle": "N/A", "file": "c.py", "line": 1,
             "title": "arbitrary file read", "reason": "", "severity": "critical"},
        ],
        "compliance": [],
    }), encoding="utf-8")


def test_drops_non_standard_principle(tmp_path):
    compiled = tmp_path / "compiled"
    _write_compiled_standard(compiled, "maintainability", ["Modularity", "Testability"])
    eval_path = tmp_path / "maintainability.json"
    _write_eval(eval_path)

    result = parse_eval_from_json(
        eval_path, "proj", "run", "maintainability", compiled_dir=compiled,
    )

    graded = [pg["principle"] for pg in result["principleGrades"] if not pg["isOverall"]]
    assert "N/A" not in graded
    assert set(graded) == {"Modularity", "Testability"}
    assert "N/A" not in {p["name"] for p in result["principles"]}


def test_keeps_all_principles_without_standard(tmp_path):
    """No compiled_dir -> permissive, backward-compatible behavior."""
    eval_path = tmp_path / "maintainability.json"
    _write_eval(eval_path)

    result = parse_eval_from_json(eval_path, "proj", "run", "maintainability")

    graded = [pg["principle"] for pg in result["principleGrades"] if not pg["isOverall"]]
    assert "N/A" in graded
