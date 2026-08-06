"""The additive markers a sink may stamp on a finding, in one enumerable place.

A marker is a field outside the core finding schema that a producer adds to
record WHY a finding looks the way it does: which gate moved its severity, or
that it came from cache rather than this scan. The severity itself reaches the
grade; the marker is the only thing that can ever explain it.

Markers are unusually easy to lose. Each one has to be threaded by hand through
a chain of serialization boundaries -- ``_VIOLATION_FIELDS``, ``build_finding``,
``Finding``, ``FindingSpec``, ``Judgment``, the evidence JSONL, the SQLite
projection, the SSE stream, the UI model -- and **no boundary raises when one is
missed**. ``_VIOLATION_FIELDS`` is a strict whitelist that silently drops unknown
keys, and ``build_finding`` returns only the fields it names. A gap produces no
error, no warning and no failing test: just a finding that quietly forgot why it
was downgraded.

That has now happened three times, once per marker that exists:

* ``carried_forward`` -- dropped on the report path, so cache-replayed findings
  reappeared as new the moment a dimension finished.
* ``provenance_downgrade`` -- missing from ``_VIOLATION_FIELDS`` and
  ``build_finding``, so a critical demoted to major lost the reason (#1044).
* ``scope_downgrade`` -- reached the per-dim JSONL but not ``events.jsonl``,
  which is what the SQL projection and the dashboard read, so a finding capped
  major -> minor showed up as an unexplained minor.

Three instances of one bug, found one at a time, each fixed only where it was
noticed. This module exists so the fourth is caught by a test instead.

**Adding a marker means adding it here.** ``tests/core/test_finding_marker_persistence.py``
is parametrized over :data:`PERSISTED_MARKERS` and will fail for any registered
marker that does not survive every boundary, so registering a new one forces its
seams closed rather than leaving them to be discovered later. Producers import
their name from here rather than defining a private literal, which is what makes
an unregistered marker visible at the definition site.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Set by ``apply_provenance_gate`` when it de-escalates a critical finding to
#: major because the evidence names no external source. A bool: the gate records
#: only THAT it fired, since the ``from`` severity is ``critical`` by construction.
PROVENANCE_DOWNGRADE = "provenance_downgrade"

#: Set by ``apply_scope_gate`` when a project's declared trust model caps a major
#: finding at minor. A dict, not a bool: the point is recovering WHICH rule fired
#: and what it waived, so the restore path can put the severity back when the
#: trust model tightens.
SCOPE_DOWNGRADE = "scope_downgrade"

#: Set by cache replay on a finding carried over from an earlier run rather than
#: produced by this scan. Not a severity gate, but the same persistence problem:
#: lose it and a replayed finding is indistinguishable from a newly found one.
CARRIED_FORWARD = "carried_forward"


@dataclass(frozen=True)
class FindingMarker:
    """A marker name plus a value a producer actually writes for it.

    *sample* is what the persistence guard round-trips. It is deliberately a
    real value from the producing code path rather than a generic sentinel:
    the markers do not share a shape (two bools and a dict), and a boundary
    that coerces -- ``bool(...)`` over a dict, say -- passes a sentinel-based
    test while corrupting the real thing.
    """

    name: str
    sample: Any


#: Every marker that must survive the full persistence path. Parametrizes the
#: guard test; see this module's docstring before adding to it.
PERSISTED_MARKERS: tuple[FindingMarker, ...] = (
    FindingMarker(PROVENANCE_DOWNGRADE, True),
    FindingMarker(
        SCOPE_DOWNGRADE,
        {"rule": "sourceless_path", "from": "major", "to": "minor"},
    ),
    FindingMarker(CARRIED_FORWARD, True),
)
