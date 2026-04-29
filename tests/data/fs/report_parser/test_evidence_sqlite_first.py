import json
from pathlib import Path

from quodeq.data.fs.report_parser._evidence import load_evidence_map
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _f(p, d, line, t="violation"):
    return {"p": p, "d": d, "file": "x.py", "line": line, "t": t,
            "severity": "medium", "reason": "r", "snippet": "s", "w": "t"}


def test_load_evidence_map_uses_sqlite_when_db_present(tmp_path: Path):
    run_dir = tmp_path
    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding(_f("P1", "timeliness", 1))
    repo.insert_finding(_f("P2", "timeliness", 2))
    repo.insert_finding(_f("P3", "security", 3))

    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()
    # No JSON files written -- forces SQLite path

    result = load_evidence_map(evidence_dir)
    assert set(result.keys()) == {"timeliness", "security"}
    assert len(result["timeliness"]["principles"]) >= 1


def test_load_evidence_map_falls_back_to_json_when_no_db(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "timeliness_evidence.json").write_text(
        '{"dimension":"timeliness","principles":{},"date":"2026-04-29"}',
    )
    result = load_evidence_map(evidence_dir)
    assert "timeliness" in result


def test_sqlite_path_includes_run_metadata_fields(tmp_path: Path):
    """SQLite-backed runs must populate sourceFileCount/date/discipline from manifest."""
    run_dir = tmp_path
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()
    # Write the run-level manifest the SQLite loader will consult
    (evidence_dir / "manifest.json").write_text(json.dumps({
        "language": "Python",
        "source_files_count": 42,
    }))

    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding(_f("P1", "timeliness", 1))

    result = load_evidence_map(evidence_dir)
    assert result["timeliness"]["sourceFileCount"] == 42
    assert result["timeliness"]["discipline"] == "Python"
    # date can be None or parseable -- accept None for now
    assert "date" in result["timeliness"]


def test_sqlite_path_handles_missing_manifest_gracefully(tmp_path: Path):
    """If manifest.json is absent (corrupt run), metadata keys are None but no crash."""
    run_dir = tmp_path
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()
    # No manifest.json written

    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding(_f("P1", "timeliness", 1))

    result = load_evidence_map(evidence_dir)
    assert result["timeliness"]["sourceFileCount"] is None
    assert result["timeliness"]["discipline"] is None


def test_read_run_data_dimension_result_has_metadata_for_sqlite_run(tmp_path: Path):
    """End-to-end: a SQLite-backed run produces DimensionResult with non-None metadata."""
    project = "proj"
    run_id = "20260429T120000"
    run_dir = tmp_path / project / run_id
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir()
    (eval_dir / "timeliness.json").write_text(json.dumps({
        "dimension": "timeliness",
        "score": 95,
        "grade": "A",
    }))
    (evidence_dir / "manifest.json").write_text(json.dumps({
        "language": "Python",
        "source_files_count": 7,
    }))

    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding(_f("P1", "timeliness", 1))

    from quodeq.data.fs.report_parser.runs import read_run_data
    dims = read_run_data(tmp_path, project, run_id)
    assert len(dims) == 1
    dim = dims[0]
    # DimensionResult should now expose the metadata
    assert dim.source_file_count == 7
    # discipline / date may have project-specific casing -- check non-None
    assert dim.discipline is not None
