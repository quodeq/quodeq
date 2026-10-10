# tests/core/scoring/test_properties.py
"""Invariants of the grade formula, checked on random principles with a fixed seed.

Adding a violation never raises a score and removing one never lowers it. Adding compliance
never lowers it. Raising a severity never raises it. Repeats change nothing. Doubling the
project changes nothing. Model severities do not move a classed rule. The label never beats
the worst severity's floor, except where the volume ceiling takes over.
"""
from __future__ import annotations

import random

import pytest

from quodeq.core.scoring.internals import (
    principle_score_and_grade, severity_grade_floor, violation_ceiling,
)
from quodeq.core.scoring.mass import principle_mass, requirement_rows
from quodeq.core.scoring.params import DEFAULT_PARAMS

LEVELS = ("minor", "major", "critical")
RULES = ("A-1", "A-2", "A-3", "U-1", "U-2", "U-3")
TRIALS = 1500
EPS = 1e-9


def _score(v, c, files):
    mass = principle_mass(requirement_rows(v, c), files, params=DEFAULT_PARAMS)
    return principle_score_and_grade(mass, params=DEFAULT_PARAMS)[0], mass


def _random_principle(rng):
    v = [{"req": rng.choice(RULES), "severity": rng.choice(LEVELS), "file": rng.choice([f"f{rng.randint(1, 40)}", None])}
         for _ in range(rng.randint(0, 25))]
    c = [{"req": rng.choice(RULES), "file": f"f{rng.randint(1, 40)}"} for _ in range(rng.randint(0, 25))]
    return v, c, rng.choice([0, 100, 500, 3000])


@pytest.fixture(scope="module")
def cases():
    rng = random.Random(3)
    return [_random_principle(rng) for _ in range(TRIALS)]


def test_p1_adding_a_violation_never_raises_and_removing_never_lowers(cases):
    rng = random.Random(1)
    for v, c, files in cases:
        s0, _ = _score(v, c, files)
        extra = {"req": rng.choice(RULES), "severity": rng.choice(LEVELS), "file": f"f{rng.randint(1, 40)}"}
        assert _score(v + [extra], c, files)[0] <= s0 + EPS
        if v:
            assert _score(v[:-1], c, files)[0] >= s0 - EPS


def test_p2_adding_compliance_never_lowers(cases):
    rng = random.Random(2)
    for v, c, files in cases:
        s0, _ = _score(v, c, files)
        assert _score(v, c + [{"req": rng.choice(RULES), "file": f"f{rng.randint(1, 40)}"}], files)[0] >= s0 - EPS


def test_p3_raising_one_severity_never_raises(cases):
    rng = random.Random(4)
    for v, c, files in cases:
        if not v:
            continue
        s0, _ = _score(v, c, files)
        i = rng.randrange(len(v))
        if v[i]["severity"] == "critical":
            continue
        raised = list(v)
        raised[i] = dict(v[i], severity=LEVELS[LEVELS.index(v[i]["severity"]) + 1])
        assert _score(raised, c, files)[0] <= s0 + EPS


def test_p4_repeats_change_nothing(cases):
    for v, c, files in cases:
        s0, _ = _score(v, c, files)
        if v:
            assert abs(_score(v + [v[0]], c, files)[0] - s0) < EPS
        if c:
            assert abs(_score(v, c + [c[0]], files)[0] - s0) < EPS


def test_p5_doubling_the_project_changes_nothing(cases):
    for v, c, files in cases:
        if files < 100:
            continue  # below the denominator floor the ratio is not preserved, by design
        s0, _ = _score(v, c, files)
        v2 = v + [dict(x, file=(x["file"] or "") + "_b") for x in v]
        c2 = c + [dict(x, file=x["file"] + "_b") for x in c]
        assert abs(_score(v2, c2, files * 2)[0] - s0) < EPS


def test_p6_raising_a_rating_never_raises_the_score(cases):
    rng = random.Random(6)
    for v, c, files in cases:
        s0, _ = _score(v, c, files)
        harsher = [dict(x, severity="critical") if rng.random() < 0.3 else x for x in v]
        assert _score(harsher, c, files)[0] <= s0 + EPS


def test_p8_label_never_beats_the_floor(cases):
    """Only the volume ceiling may push a score below its severity floor."""
    for v, c, files in cases:
        s, mass = _score(v, c, files)
        if mass.violation_mass == 0:
            assert s == 10.0
            continue
        floor = severity_grade_floor(mass.worst, params=DEFAULT_PARAMS)
        ceiling = round(violation_ceiling(mass.violation_mass, params=DEFAULT_PARAMS), 1)
        assert s >= floor - EPS or s == ceiling


def test_counterexamples_from_the_rigour_pass():
    """The two cases that broke the mode-based design: a duplicate minor under a mostly-major
    rule, and one critical outlier in a 300-file minor rule."""
    files = 3000
    v = [{"req": "U-1", "file": "a", "severity": "major"}, {"req": "U-1", "file": "b", "severity": "minor"}]
    s0, _ = _score(v, [], files)
    assert abs(_score(v + [v[1]], [], files)[0] - s0) < EPS
    minor_rule = [{"req": "U-2", "file": f"f{i}", "severity": "minor"} for i in range(300)]
    base, _ = _score(minor_rule, [{"req": "U-3", "file": f"g{i}"} for i in range(100)], files)
    outlier = minor_rule[:-1] + [dict(minor_rule[-1], severity="critical")]
    with_outlier, _ = _score(outlier, [{"req": "U-3", "file": f"g{i}"} for i in range(100)], files)
    assert base - 2.5 < with_outlier < base  # one file's worth, not a re-label of the rule
