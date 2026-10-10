"""The severity floor must not override the volume ceiling.

`severity_grade_floor` says "only minor issues, so you can't be that bad".
`violation_ceiling` says "this much violation load caps you". They are both
guards, and they cross when a principle has a LOT of issues that happen to all
be minor. The clamp resolved that by letting the floor win unconditionally:

    final = max(floor, min(ceil, raw))

so `usability Learnability` on the quodeq project -- 250 distinct minor
violation types, 0 major, 0 critical -- came out at floor=8.0 ("Good") while
the ceiling said 7.01 and the curve said 3.35. The one guard that encodes
VOLUME was the one discarded, which is precisely what made 269 findings
invisible to the grade.

Clamping to the floor first and the ceiling last keeps the ceiling
authoritative. Note the two orderings are algebraically identical whenever
floor <= ceil, which is every other principle on that project (34 of 35), so
this only ever moves the contradictory case.
"""
from __future__ import annotations

from quodeq.core.scoring.internals import clamp_principle_score, severity_grade_floor, violation_ceiling
from quodeq.core.scoring.mass import principle_mass, requirement_rows
from quodeq.core.scoring.params import DEFAULT_PARAMS


def test_a_pile_of_minor_rules_cannot_read_above_the_ceiling() -> None:
    """Many minor-only rules across every file of a project: the floor sits above the ceiling."""
    files = 100
    violations = [
        {"req": f"U-LRN-{i}", "file": f"f{j}.py", "severity": "minor"}
        for i in range(1000) for j in range(files)
    ]
    mass = principle_mass(requirement_rows(violations, []), files, params=DEFAULT_PARAMS)
    floor = severity_grade_floor(mass.worst, params=DEFAULT_PARAMS)
    ceil = violation_ceiling(mass.violation_mass, params=DEFAULT_PARAMS)
    assert ceil < floor, "the minor-only floor sits above the volume ceiling"
    assert clamp_principle_score(9.0, mass.violation_mass, mass.worst, params=DEFAULT_PARAMS) == round(ceil, 1)
