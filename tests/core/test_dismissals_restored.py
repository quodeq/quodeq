"""``restored_fingerprints``: the code a user has put back is off limits to precedent (#1208).

A precedent auto-dismissal must never re-hide code the user restored. The
net answer per ``(req, fingerprint)`` is whatever the LAST event said, in
any file: dismiss then restore is restored; dismiss, restore, dismiss again
is not.
"""
from __future__ import annotations

from quodeq.core.dismissals import restored_fingerprints
from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
)


def _dismiss(req: str, file: str, fp: str | None) -> FindingDismissedEvent:
    return FindingDismissedEvent(payload=FindingDismissed(req=req, file=file, line=1, fingerprint=fp))


def _restore(req: str, file: str, fp: str | None) -> FindingUndismissedEvent:
    return FindingUndismissedEvent(payload=FindingUndismissed(req=req, file=file, line=1, fingerprint=fp))


def test_dismiss_then_restore_is_restored() -> None:
    events = [_dismiss("R1", "a.py", "fp1"), _restore("R1", "a.py", "fp1")]
    assert restored_fingerprints(events) == frozenset({("R1", "fp1")})


def test_restore_then_dismiss_again_is_not_restored() -> None:
    events = [_dismiss("R1", "a.py", "fp1"), _restore("R1", "a.py", "fp1"), _dismiss("R1", "b.py", "fp1")]
    assert restored_fingerprints(events) == frozenset()


def test_restore_is_keyed_on_code_not_file() -> None:
    # Dismiss in one file, restore from a different one: the net answer must
    # still track (req, fingerprint), not the file the restore event carried.
    events = [_dismiss("R1", "a.py", "fp1"), _restore("R1", "b.py", "fp1")]
    restored = restored_fingerprints(events)
    assert ("R1", "fp1") in restored


def test_line_keyed_restores_are_ignored() -> None:
    events = [_dismiss("R1", "a.py", None), _restore("R1", "a.py", None)]
    assert restored_fingerprints(events) == frozenset()
