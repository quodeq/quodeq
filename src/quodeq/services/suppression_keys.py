"""Pure suppression predicates — the identity-key layer.

Dismiss and delete use different identity keys, and those keys have drifted
from their consumers before (a dismiss filter matching on principle name
while the finding dicts carried practiceId, so the filter sat inert). Every
reader that has to answer "would the dashboard hide this finding?" must use
these predicates rather than re-deriving keys:

- dismissed: ``(req, file, line)``            -- one finding, exact line
- deleted:   ``(dimension, principle, file)`` -- whole principle in a file

This module is import-leaf by design: ``suppression``, ``dismissed`` and
``deleted`` all depend on it, which is what broke their three-way deferred
import cycle.
"""
from __future__ import annotations

def _coerce_line(line: object) -> int:
    try:
        return int(line)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def is_dismissed(
    dismissed: frozenset | set, *, req: str | None, principle: str | None = "",
    file: str | None = "", line: object = 0,
) -> bool:
    """True when the dismiss store hides this finding.

    A finding's dismiss identity is its ``req``, falling back to its principle
    when it has none -- the same ``req || principle`` the UI stores
    (buildDismissPayload). Every read side must apply the same fallback, or a
    no-req finding disappears from the counters while its grade never moves.

    For a no-req finding the assistant's draft/apply path records the key with
    an empty req (``("", file, line)``, see tests/assistant/
    test_dismiss_apply_e2e.py), and older stores may hold either form -- so
    both are accepted.
    """
    if not dismissed:
        return False
    file_key = file or ""
    line_key = _coerce_line(line)
    if (req or principle or "", file_key, line_key) in dismissed:
        return True
    return not req and ("", file_key, line_key) in dismissed


def is_deleted(
    deleted: frozenset | set, *, dimension: str | None,
    principle: str | None, file: str | None,
) -> bool:
    """True when the delete store hides this finding's whole principle+file."""
    if not deleted:
        return False
    return (dimension or "", principle or "", file or "") in deleted
