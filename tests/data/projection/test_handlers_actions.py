from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
    Judgment,
)
from quodeq.data.projection.handlers import handle
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.data.sqlite.connection import open_evaluation_db


def _seed_finding(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1",
    ))


def _verdict_for(tmp_path: Path, req: str, file: str, line: int) -> str | None:
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings WHERE requirement=? AND file=? AND line=?",
            (req, file, line),
        ).fetchone()
    return row[0] if row else None


def test_handle_finding_dismissed_flips_verdict(tmp_path: Path) -> None:
    _seed_finding(tmp_path)
    store = SQLiteStateStore(tmp_path)

    event = FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    handle(event, store)

    assert _verdict_for(tmp_path, "R1", "a.py", 10) == "dismissed"


def test_handle_finding_undismissed_restores_violation(tmp_path: Path) -> None:
    _seed_finding(tmp_path)
    store = SQLiteStateStore(tmp_path)
    handle(FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10)), store)

    handle(FindingUndismissedEvent(payload=FindingUndismissed(req="R1", file="a.py", line=10)), store)

    assert _verdict_for(tmp_path, "R1", "a.py", 10) == "violation"


def _verdict_at(tmp_path: Path, file: str, line: int) -> str | None:
    """Verdict of the finding stored with a NULL requirement at (file, line)."""
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings "
            "WHERE requirement IS NULL AND file=? AND line=?",
            (file, line),
        ).fetchone()
    return row[0] if row else None


def test_handle_dismissed_flips_verdict_for_finding_without_req(tmp_path: Path) -> None:
    """A finding with no requirement id is stored with requirement NULL. The
    dismiss event carries an empty req, so matching on `requirement = ''` never
    hits it and the score never moves. The verdict must still flip, matched on
    (file, line)."""
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req=None,
    ))

    handle(FindingDismissedEvent(payload=FindingDismissed(req="", file="a.py", line=10)), store)

    assert _verdict_at(tmp_path, "a.py", 10) == "dismissed"


def test_handle_undismissed_restores_finding_without_req(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req=None,
    ))
    handle(FindingDismissedEvent(payload=FindingDismissed(req="", file="a.py", line=10)), store)

    handle(FindingUndismissedEvent(payload=FindingUndismissed(req="", file="a.py", line=10)), store)

    assert _verdict_at(tmp_path, "a.py", 10) == "violation"


def test_dismiss_empty_req_does_not_touch_req_bearing_finding_at_same_location(tmp_path: Path) -> None:
    """Dismissing the null-req finding must not sweep a different finding that
    carries a req at the same (file, line)."""
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req=None,
    ))
    store.record_finding(Judgment(
        practice_id="P2", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1",
    ))

    handle(FindingDismissedEvent(payload=FindingDismissed(req="", file="a.py", line=10)), store)

    assert _verdict_at(tmp_path, "a.py", 10) == "dismissed"      # null-req one
    assert _verdict_for(tmp_path, "R1", "a.py", 10) == "violation"  # req one untouched


def test_handle_dismissed_no_op_when_finding_absent(tmp_path: Path) -> None:
    # Project A's actions log may contain dismissals for findings that this
    # run never produced. The handler should silently no-op.
    store = SQLiteStateStore(tmp_path)
    handle(FindingDismissedEvent(payload=FindingDismissed(req="R999", file="x.py", line=1)), store)

    assert _verdict_for(tmp_path, "R999", "x.py", 1) is None
