"""The run report records how many findings were quarantined.

Quarantined findings are correctly kept out of scoring: they carry no principle
the standard defines, so they have no card, no radial vertex and no dimension
score. But dropping them without a trace makes the grade unexplainable from what
a reader can see -- a run that discarded 200 of 571 findings looks identical to a
clean one, and its grade was computed from a fraction of the evidence.

So the COUNT is run metadata, in the same tier as ``coveragePct``, ``filesRead``
and ``exitReason``: it does not change the grade, it tells you how much to trust
it. Deliberately not a findings bucket -- that would rebuild the phantom "N/A"
principle card removed in #659/#663/#721.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis._report_assembly import build_dashboard_report
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.data.fs.standards_loader import read_req_to_principle_map

_DIMENSION = "demo"


@pytest.fixture
def compiled_dir(tmp_path: Path) -> Path:
    d = tmp_path / "compiled"
    d.mkdir()
    (d / f"{_DIMENSION}.json").write_text(json.dumps({
        "id": _DIMENSION,
        "principles": [
            {"name": "Analyzability", "requirements": [{"id": "D-ANA-1"}]},
        ],
    }), encoding="utf-8")
    return d


@pytest.fixture
def evidence_file(tmp_path: Path) -> Path:
    rows = [
        {"p": "Analyzability", "req": "D-ANA-1", "t": "violation",
         "d": _DIMENSION, "file": "a.py", "line": 1},
        # Unmappable: resolves to the phantom "N/A" principle.
        {"req": "N/A", "t": "violation", "d": _DIMENSION,
         "file": "b.py", "line": 2, "severity": "critical"},
    ]
    p = tmp_path / "evidence.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _context() -> EvidenceContext:
    return EvidenceContext(
        language=_DIMENSION, repository="demo-repo", date_str="2026-07-25",
        source_file_count=2, files_read=2,
    )


def test_evidence_carries_the_quarantined_count(evidence_file, compiled_dir):
    evidence = parse_jsonl_to_evidence(evidence_file, _context(), compiled_dir=compiled_dir,
                                       req_map_reader=read_req_to_principle_map)
    assert evidence.quarantined_count == 1
    # Still excluded from scoring: no phantom principle was created.
    assert set(evidence.principles) == {"Analyzability"}


def test_report_json_records_the_quarantined_count(evidence_file, compiled_dir):
    evidence = parse_jsonl_to_evidence(evidence_file, _context(), compiled_dir=compiled_dir,
                                       req_map_reader=read_req_to_principle_map)
    report = build_dashboard_report(evidence, {})
    assert report["quarantinedCount"] == 1
    # The quarantined finding is metadata only -- it never joins the findings list.
    assert report["totals"]["violationCount"] == 1
    assert len(report["violations"]) == 1


def test_clean_run_records_zero(tmp_path, compiled_dir):
    p = tmp_path / "evidence.jsonl"
    p.write_text(json.dumps({
        "p": "Analyzability", "t": "violation", "d": _DIMENSION,
        "file": "a.py", "line": 1,
    }) + "\n", encoding="utf-8")
    evidence = parse_jsonl_to_evidence(p, _context(), compiled_dir=compiled_dir,
                                       req_map_reader=read_req_to_principle_map)
    assert build_dashboard_report(evidence, {})["quarantinedCount"] == 0


def test_no_standard_quarantines_nothing(evidence_file):
    """Without a standard there is no membership to fail, so nothing is dropped."""
    evidence = parse_jsonl_to_evidence(evidence_file, _context())
    assert evidence.quarantined_count == 0
    assert build_dashboard_report(evidence, {})["quarantinedCount"] == 0


def _write_report(run_dir: Path, dimension: str, extra: dict) -> None:
    d = run_dir / "evaluation"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{dimension}.json").write_text(json.dumps({
        "schema_version": 1, "dimension": dimension,
        "overallScore": "7.0/10", "overallGrade": "good",
        "filesRead": 10, "sourceFileCount": 10, "exitReason": "done",
        "principles": [], "violations": [], "compliance": [],
        **extra,
    }), encoding="utf-8")


def test_count_survives_the_run_read_into_the_dashboard_payload(tmp_path):
    """DimensionResult is a strict whitelist: a field it does not name is dropped.

    Writing the count into the report JSON is not enough on its own -- the run
    read maps every dimension through that dataclass, so a new key silently
    vanishes before the UI ever sees it and the feature is inert. Pin the whole
    path: report JSON -> DimensionResult -> camelCase payload.
    """
    from quodeq.core.types import to_camel_dict
    from quodeq.data.fs.report_parser.runs import read_run_data

    _write_report(tmp_path / "proj" / "run1", "demo", {"quarantinedCount": 3})
    result = read_run_data(tmp_path, "proj", "run1")[0]
    assert result.quarantined_count == 3
    assert to_camel_dict(result)["quarantinedCount"] == 3


def test_reports_written_before_the_field_read_as_zero(tmp_path):
    from quodeq.data.fs.report_parser.runs import read_run_data

    _write_report(tmp_path / "proj" / "run1", "legacy", {})
    assert read_run_data(tmp_path, "proj", "run1")[0].quarantined_count == 0
