"""The SQL projection sets verdicts from the net dismissed state.

``SQLiteStateStore.apply_dismissed_state`` is the one write the actions
replay makes. It decides membership with ``DismissedKeys.matches`` -- the same
predicate the services read side uses -- so these tests pin the identity
rules on the SQL surface: fingerprint first, line for snippet-less findings,
``req || principle`` for findings without a requirement.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
    Judgment,
)
from quodeq.core.dismissals import fold_dismissals
from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.data.projection.handlers import handle
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.data.sqlite.connection import open_evaluation_db

SNIPPET = "password = 'secret'"
FP = snippet_fingerprint("R1", SNIPPET)


def _seed(tmp_path: Path, **kw) -> None:
    defaults = dict(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", snippet=SNIPPET,
    )
    SQLiteStateStore(tmp_path).record_finding(Judgment(**{**defaults, **kw}))


def _dismiss(req: str, file: str, line: int, fingerprint: str | None = None) -> FindingDismissedEvent:
    return FindingDismissedEvent(payload=FindingDismissed(
        req=req, file=file, line=line, fingerprint=fingerprint))


def _undismiss(req: str, file: str, line: int, fingerprint: str | None = None) -> FindingUndismissedEvent:
    return FindingUndismissedEvent(payload=FindingUndismissed(
        req=req, file=file, line=line, fingerprint=fingerprint))


def _apply(tmp_path: Path, *events) -> int:
    return SQLiteStateStore(tmp_path).apply_dismissed_state(fold_dismissals(events))


def _verdict_for(tmp_path: Path, file: str, line: int) -> str | None:
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings WHERE file=? AND line=?", (file, line),
        ).fetchone()
    return row[0] if row else None


def test_fingerprinted_dismiss_flips_verdict(tmp_path: Path) -> None:
    _seed(tmp_path)

    assert _apply(tmp_path, _dismiss("R1", "a.py", 10, FP)) == 1

    assert _verdict_for(tmp_path, "a.py", 10) == "dismissed"


def test_fingerprinted_dismiss_follows_the_finding_to_its_new_line(tmp_path: Path) -> None:
    """The whole point of #1165: the run holds the same code twelve lines down."""
    _seed(tmp_path, line=22)

    _apply(tmp_path, _dismiss("R1", "a.py", 10, FP))

    assert _verdict_for(tmp_path, "a.py", 22) == "dismissed"


def test_fingerprinted_dismiss_ignores_different_code_at_the_old_line(tmp_path: Path) -> None:
    _seed(tmp_path, line=10, snippet="token = os.environ['T']")

    _apply(tmp_path, _dismiss("R1", "a.py", 10, FP))

    assert _verdict_for(tmp_path, "a.py", 10) == "violation"


def test_line_keyed_dismiss_still_matches_by_line(tmp_path: Path) -> None:
    """Legacy entries (no fingerprint) keep their exact-line identity."""
    _seed(tmp_path)

    _apply(tmp_path, _dismiss("R1", "a.py", 10))

    assert _verdict_for(tmp_path, "a.py", 10) == "dismissed"


def test_snippet_less_finding_matches_a_fingerprinted_entry_by_line(tmp_path: Path) -> None:
    """A row without a snippet has only its line as identity."""
    _seed(tmp_path, snippet="")

    _apply(tmp_path, _dismiss("R1", "a.py", 10, FP))

    assert _verdict_for(tmp_path, "a.py", 10) == "dismissed"


def test_undismiss_restores_violation(tmp_path: Path) -> None:
    _seed(tmp_path)

    _apply(tmp_path, _dismiss("R1", "a.py", 10, FP))
    changed = _apply(tmp_path, _dismiss("R1", "a.py", 10, FP), _undismiss("R1", "a.py", 10, FP))

    assert changed == 1
    assert _verdict_for(tmp_path, "a.py", 10) == "violation"


def test_unchanged_state_writes_nothing(tmp_path: Path) -> None:
    _seed(tmp_path)
    _apply(tmp_path, _dismiss("R1", "a.py", 10, FP))

    assert _apply(tmp_path, _dismiss("R1", "a.py", 10, FP)) == 0


def test_finding_without_req_matches_the_empty_req_form(tmp_path: Path) -> None:
    """The assistant records a no-req finding under an empty req."""
    _seed(tmp_path, req=None, snippet="")

    _apply(tmp_path, _dismiss("", "a.py", 10))

    assert _verdict_for(tmp_path, "a.py", 10) == "dismissed"


def test_finding_without_req_matches_the_principle_form(tmp_path: Path) -> None:
    """The UI records a no-req finding under its principle (``req || principle``);
    the SQL projection used to miss those entirely."""
    _seed(tmp_path, req=None)

    _apply(tmp_path, _dismiss("P1", "a.py", 10, snippet_fingerprint("P1", SNIPPET)))

    assert _verdict_for(tmp_path, "a.py", 10) == "dismissed"


def test_empty_req_dismiss_does_not_touch_req_bearing_finding_at_same_location(tmp_path: Path) -> None:
    _seed(tmp_path, req="R1")

    _apply(tmp_path, _dismiss("", "a.py", 10))

    assert _verdict_for(tmp_path, "a.py", 10) == "violation"


def test_compliance_rows_are_never_touched(tmp_path: Path) -> None:
    _seed(tmp_path, verdict="compliance")

    assert _apply(tmp_path, _dismiss("R1", "a.py", 10, FP), _dismiss("R1", "a.py", 10)) == 0
    assert _verdict_for(tmp_path, "a.py", 10) == "compliance"


def test_absent_finding_is_a_no_op(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)

    assert store.apply_dismissed_state(fold_dismissals([_dismiss("R1", "a.py", 10, FP)])) == 0


def test_handle_ignores_action_events(tmp_path: Path) -> None:
    """Dismiss events are not handled per event any more; ``handle`` skips them."""
    _seed(tmp_path)

    handle(_dismiss("R1", "a.py", 10, FP), SQLiteStateStore(tmp_path))

    assert _verdict_for(tmp_path, "a.py", 10) == "violation"
