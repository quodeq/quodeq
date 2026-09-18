"""The net dismissed state of a project and its one membership predicate.

Two replay paths fold ``actions.jsonl``: the services read side
(``services.dismissed.dismissed_keys``) and the SQL projection
(``data.projection.engine``). Both call :func:`fold_dismissals` and decide
membership with :meth:`DismissedKeys.matches`, so a finding cannot be hidden
on one surface and visible on another. Identity rules and key shapes are in
``core.finding_identity``.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from quodeq.core.events.models import BaseEvent, EventType
from quodeq.core.finding_identity import (
    DismissKey,
    coerce_line,
    dismiss_identities,
    snippet_fingerprint,
)


@dataclass(frozen=True, slots=True)
class DismissedEntry:
    """One net-dismissed finding as recorded in the actions log.

    ``fingerprint`` is None for entries whose finding has no snippet and for
    legacy entries the backfill could not resolve; those match on ``line``.
    ``reason`` and ``dismissed_at`` are display data, not identity.
    """

    req: str
    file: str
    line: int
    fingerprint: str | None = None
    reason: str | None = field(default=None, compare=False)
    dismissed_at: datetime | None = field(default=None, compare=False)

    @property
    def key(self) -> DismissKey:
        """The bare-tuple form: fingerprint key when fingerprinted, else line key."""
        if self.fingerprint:
            return (self.req, self.file, self.fingerprint)
        return self.line_key

    @property
    def line_key(self) -> tuple[str, str, int]:
        """The ``(req, file, line)`` form, held for every entry whether fingerprinted or not.

        It is what a snippet-less finding matches on, so it stays populated
        even when ``key`` returns the fingerprint tuple.
        """
        return (self.req, self.file, self.line)


def _entry_order(entry: DismissedEntry) -> tuple:
    return (entry.req, entry.file, entry.line, entry.fingerprint or "")


@dataclass(frozen=True)
class DismissedKeys:
    """The net dismissed state of a project, with the one membership predicate.

    ``fingerprints`` holds ``(req, file, fingerprint)`` for fingerprinted
    entries; ``lines`` holds every entry's ``(req, file, line)`` and
    ``unresolved_lines`` only those of entries without a fingerprint. A
    finding with a snippet matches on its fingerprint, or on its line against
    an unresolved entry. A finding without a snippet matches on its line
    against any entry: the line is all the identity it has.
    """

    entries: tuple[DismissedEntry, ...] = ()
    fingerprints: frozenset[tuple[str, str, str]] = field(
        init=False, repr=False, compare=False, default=frozenset())
    lines: frozenset[tuple[str, str, int]] = field(
        init=False, repr=False, compare=False, default=frozenset())
    unresolved_lines: frozenset[tuple[str, str, int]] = field(
        init=False, repr=False, compare=False, default=frozenset())

    def __post_init__(self) -> None:
        fps = frozenset(
            (e.req, e.file, e.fingerprint) for e in self.entries if e.fingerprint)
        object.__setattr__(self, "fingerprints", fps)
        object.__setattr__(self, "lines", frozenset(e.line_key for e in self.entries))
        object.__setattr__(self, "unresolved_lines", frozenset(
            e.line_key for e in self.entries if not e.fingerprint))

    @classmethod
    def from_line_keys(cls, keys: Iterable[tuple]) -> DismissedKeys:
        """Adopt a bare ``{(req, file, line)}`` set (legacy key form)."""
        entries = sorted(
            (DismissedEntry(str(r or ""), str(f or ""), coerce_line(line))
             for r, f, line in keys),
            key=_entry_order,
        )
        return cls(entries=tuple(entries))

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def line_keys(self) -> set[tuple[str, str, int]]:
        """Every entry's ``(req, file, line)``, for display and legacy callers."""
        return set(self.lines)

    def matches(
        self, *, req: str | None, principle: str | None = "", file: str | None = "",
        line: object = 0, snippet: str | None = None,
    ) -> bool:
        """True when this state hides the finding (no pattern rules here)."""
        if not self.entries:
            return False
        file_key = file or ""
        line_key = coerce_line(line)
        for ident in dismiss_identities(req, principle):
            fp = snippet_fingerprint(ident, snippet)
            if fp is None:
                if (ident, file_key, line_key) in self.lines:
                    return True
                continue
            if (ident, file_key, fp) in self.fingerprints:
                return True
            if (ident, file_key, line_key) in self.unresolved_lines:
                return True
        return False

    def touching(self, run_keys: Iterable[DismissKey]) -> DismissedKeys:
        """Entries that can hide a finding of a run with these dismiss keys.

        *run_keys* is a run's ``finding_dismiss_keys`` union. Membership is
        checked on the entry's own key plus its line key, mirroring
        :meth:`matches` for snippet-less rows.
        """
        present = set(run_keys)
        kept = tuple(
            e for e in self.entries if e.key in present or e.line_key in present)
        return DismissedKeys(entries=kept)

    def version_payload(self) -> list[list]:
        """Deterministic JSON-able form for cache-version hashes."""
        return [[e.req, e.file, e.line, e.fingerprint or ""] for e in self.entries]

    def entries_at(self, req: str, file: str, line: int) -> tuple[DismissedEntry, ...]:
        """Entries recorded for this ``(req, file, line)``, any identity form."""
        key = (req, file, line)
        return tuple(e for e in self.entries if e.line_key == key)


EMPTY_DISMISSED = DismissedKeys()


def _line_identity(req: str, file: str, line: int) -> tuple:
    return ("line", req, file, line)


def _fp_identity(req: str, file: str, fp: str) -> tuple:
    return ("fp", req, file, fp)


def fold_dismissals(events: Iterable[BaseEvent]) -> DismissedKeys:
    """Replay dismiss/undismiss events, in order, into the net dismissed state.

    A fingerprinted dismiss supersedes the line-keyed entry for the same
    ``(req, file, line)``: that is how the one-shot backfill upgrades legacy
    entries without rewriting the log. An undismiss removes the entry it names
    and the line-keyed twin of the same finding; a legacy undismiss (no
    fingerprint) removes every entry recorded at its ``(req, file, line)``,
    since "restore this finding" is all the older client could say.
    Events of other types are ignored.
    """
    active: dict[tuple, DismissedEntry] = {}
    for event in events:
        event_type = event.event_type
        if event_type not in (EventType.FINDING_DISMISSED, EventType.FINDING_UNDISMISSED):
            continue
        payload = event.payload
        req = str(payload.req or "")
        file = str(payload.file or "")
        line = coerce_line(payload.line)
        fp = getattr(payload, "fingerprint", None) or None
        if event_type == EventType.FINDING_DISMISSED:
            entry = DismissedEntry(
                req, file, line, fp,
                reason=getattr(payload, "reason", None),
                dismissed_at=getattr(event, "timestamp", None),
            )
            if fp:
                active.pop(_line_identity(req, file, line), None)
                active[_fp_identity(req, file, fp)] = entry
            else:
                active[_line_identity(req, file, line)] = entry
            continue
        active.pop(_line_identity(req, file, line), None)
        if fp:
            active.pop(_fp_identity(req, file, fp), None)
            continue
        for identity in [
            k for k, e in active.items()
            if k[0] == "fp" and e.req == req and e.file == file and e.line == line
        ]:
            active.pop(identity, None)
    entries = tuple(sorted(active.values(), key=_entry_order))
    return DismissedKeys(entries=entries)
