from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.projection.grade_projector import compute_run_grades
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _seed(store, req, file, severity="minor"):
    store.record_finding(Judgment(practice_id="P1", verdict="violation", dimension="Security",
                                  file=file, line=1, reason="r", req=req, severity=severity))


def test_compute_run_grades_takes_classes_explicitly(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    for i in range(20):
        _seed(store, "S-INT-2", f"f{i}.py")
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "security.json").write_text('{"sourceFileCount": 1000}')
    loose = compute_run_grades(tmp_path, DEFAULT_PARAMS, classes={})[1][0]["score"]
    pinned = compute_run_grades(tmp_path, DEFAULT_PARAMS, classes={"S-INT-2": "critical"})[1][0]["score"]
    assert pinned < loose
