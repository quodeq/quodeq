"""Pure suppression predicates — the identity-key layer.

Dismiss and delete use different identity keys, and those keys have drifted
from their consumers before (a dismiss filter matching on principle name
while the finding dicts carried practiceId, so the filter sat inert). Every
reader that has to answer "would the dashboard hide this finding?" must use
these predicates rather than re-deriving keys:

- dismissed: ``(req, file, snippet fingerprint)``, falling back to
  ``(req, file, line)`` for findings without a snippet and for legacy entries
  the backfill could not resolve -- see ``core.finding_identity``
- deleted:   ``(dimension, principle, file)`` -- whole principle in a file

This module is import-leaf by design: ``suppression``, ``dismissed`` and
``deleted`` all depend on it, which is what broke their three-way deferred
import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch

from quodeq.core.dismissals import EMPTY_DISMISSED, DismissedKeys
from quodeq.core.types.suppression_rule import SuppressionRule


@dataclass(frozen=True)
class SuppressionKeys:
    """Dismissed state, deleted violation keys and pattern rules for one project."""
    dismissed: "DismissedKeys | frozenset | set[tuple]"
    deleted: "frozenset | set[tuple]" = frozenset()
    rules: "tuple[SuppressionRule, ...]" = ()


@dataclass(frozen=True, slots=True)
class FindingRef:
    """The identity the dismiss store matches a finding on.

    ``req`` falls back to ``principle`` when the finding has none. With a
    ``snippet`` the match runs on its fingerprint; without one only ``line``
    identifies the finding.
    """

    req: str | None
    principle: str | None = ""
    file: str | None = ""
    line: object = 0
    snippet: str | None = None


def as_dismissed_keys(dismissed: "DismissedKeys | frozenset | set | None") -> DismissedKeys:
    """Accept the dismissed state or the legacy bare ``{(req, file, line)}`` set.

    Production readers hand over the ``DismissedKeys`` that
    ``services.dismissed.dismissed_keys`` returns; the bare set form stays
    accepted for callers and tests that build line keys by hand.
    """
    if isinstance(dismissed, DismissedKeys):
        return dismissed
    if not dismissed:
        return EMPTY_DISMISSED
    return DismissedKeys.from_line_keys(dismissed)


def matches_suppression_rule(
    rules: "tuple[SuppressionRule, ...]", req: str, file: str,
) -> bool:
    """True when any rule accepts this ``(req, file)`` pair.

    Both parts must be non-empty: a finding with no requirement or no file
    cannot be matched against a pattern without matching far too much.
    ``**`` in the file glob spans directories (fnmatch's ``*`` already
    crosses separators, so both forms work).
    """
    if not rules or not req or not file:
        return False
    return any(
        fnmatch(req, rule.req) and fnmatch(file, rule.file)
        for rule in rules
    )


def is_dismissed(
    dismissed: "DismissedKeys | frozenset | set", ref: FindingRef, *,
    rules: "tuple[SuppressionRule, ...]" = (),
) -> bool:
    """True when the dismiss store hides the finding *ref* describes.

    A finding's dismiss identity is its ``req``, falling back to its principle
    when it has none -- the same ``req || principle`` the UI stores
    (buildDismissPayload). Every read side must apply the same fallback, or a
    no-req finding disappears from the counters while its grade never moves.
    For a no-req finding the assistant's draft/apply path records the key with
    an empty req (see tests/assistant/test_dismiss_apply_e2e.py), so both
    forms are accepted.

    Pass the finding's ``snippet`` in *ref*: with it the match runs on the
    snippet fingerprint and survives the line shifts every refactor causes.
    Without it only the line can identify the finding.
    """
    file_key = ref.file or ""
    # Pattern rules are checked first and independently of the key store: a
    # rule stays true after a refactor shifts the line the exact key pinned.
    if matches_suppression_rule(rules, ref.req or ref.principle or "", file_key):
        return True
    if not dismissed:
        return False
    return as_dismissed_keys(dismissed).matches(
        req=ref.req, principle=ref.principle, file=file_key, line=ref.line,
        snippet=ref.snippet)


def is_deleted(
    deleted: frozenset | set, *, dimension: str | None,
    principle: str | None, file: str | None,
) -> bool:
    """True when the delete store hides this finding's whole principle+file."""
    if not deleted:
        return False
    return (dimension or "", principle or "", file or "") in deleted
