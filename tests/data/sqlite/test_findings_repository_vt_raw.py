"""violation_type_raw round-trips through evaluation.db on both write paths."""
from __future__ import annotations

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.data.sqlite.state_store import SQLiteStateStore


def test_repository_round_trips_vt_raw(tmp_path):
    repo = SqliteFindingsRepository(tmp_path)
    assert repo.insert_finding({
        "schema_version": 1, "p": "Fault Tolerance", "d": "reliability", "req": "R-FT-1",
        "t": "violation", "severity": "minor", "file": "a.py", "line": 3,
        "w": "t", "reason": "r", "vt": "Empty_Catch", "vt_raw": "Empty_Catch",
    })
    [finding] = repo.list_by_dimension("reliability")
    assert finding.violation_type == "Empty_Catch"
    assert finding.violation_type_raw == "Empty_Catch"


def test_state_store_records_violation_type_raw(tmp_path):
    SQLiteStateStore(tmp_path).record_finding(Judgment(
        practice_id="FT", verdict="violation", dimension="reliability",
        file="a.py", line=3, reason="r", severity="minor", violation_type_raw="X",
    ))
    with open_evaluation_db(tmp_path) as conn:
        assert conn.execute("SELECT violation_type_raw FROM findings").fetchone() == ("X",)
