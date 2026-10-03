"""explain_dimension returns the grade tables' numbers with their stages."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.grade_explain import explain_dimension

_PROJECT = "proj"
_RUN = "run-1"
_DIM = "Security"
_SCORABLE = 5  # clears the medium-confidence floor so P1 is graded, not Insufficient


def _finding(i: int, *, practice: str, verdict: str = "violation") -> dict:
    return dict(practice_id=practice, verdict=verdict, dimension=_DIM, file=f"f{i}.py",
                line=10 + i, reason="r", req=f"R{i}", severity="major")


def _seed(reports_root: Path, findings: list[dict]) -> None:
    run_dir = reports_root / _PROJECT / _RUN
    run_dir.mkdir(parents=True)
    writer = EventLogWriter(run_dir / "events.jsonl")
    for f in findings:
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**f)))
    Projector().ensure_projected(run_dir / "events.jsonl", run_dir, project_dir=reports_root / _PROJECT)


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    findings = [_finding(i, practice="P1") for i in range(_SCORABLE)]
    findings.append(_finding(99, practice="P2"))  # one finding: Insufficient
    findings.append(_finding(98, practice=""))    # no principle: not a card, not a row
    _seed(tmp_path, findings)
    return tmp_path


def test_explain_matches_the_grade_table(seeded: Path) -> None:
    out = explain_dimension(seeded, _PROJECT, _RUN, _DIM)
    graded = {p["principleId"]: p for p in out["principles"]}
    rows = {r["principle_id"]: r for r in SQLiteStateStore(seeded / _PROJECT / _RUN).read_principle_grades()}
    assert graded["P1"]["stages"]["final"] == rows["P1"]["score"]
    assert graded["P1"]["stages"]["grade"] == rows["P1"]["grade"]
    assert graded["P1"]["stages"]["types"]["major"] == _SCORABLE
    assert out["params"]["baseK"] == pytest.approx(0.12)


def test_insufficient_principle_has_no_stages(seeded: Path) -> None:
    out = explain_dimension(seeded, _PROJECT, _RUN, _DIM)
    p2 = next(p for p in out["principles"] if p["principleId"] == "P2")
    assert (p2["insufficient"], p2["stages"], p2["findings"]) == (True, None, 1)


def test_dimension_lookup_is_case_insensitive(seeded: Path) -> None:
    assert explain_dimension(seeded, _PROJECT, _RUN, "security")["dimension"] == "security"


def test_unknown_dimension_is_not_found(seeded: Path) -> None:
    with pytest.raises(FileNotFoundError):
        explain_dimension(seeded, _PROJECT, _RUN, "usability")


def test_unknown_run_is_not_found(seeded: Path) -> None:
    with pytest.raises(FileNotFoundError):
        explain_dimension(seeded, _PROJECT, "nope", _DIM)


def test_findings_without_a_principle_are_not_listed(seeded: Path) -> None:
    ids = [p["principleId"] for p in explain_dimension(seeded, _PROJECT, _RUN, _DIM)["principles"]]
    assert ids == ["P1", "P2"]
