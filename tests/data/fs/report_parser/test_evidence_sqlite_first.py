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
