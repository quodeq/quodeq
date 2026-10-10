"""Golden: the OWASP BenchmarkJava security run grades as the spec says (section 8).

The fixture is a real Sonnet run of BenchmarkJava v1.2 (2803 source files),
reduced to per-rule file counts by severity and per-rule compliance file
counts. The project is a deliberately vulnerable benchmark, so its security
grade must sit low; the pre-v4 formula stored 3.5. Each principle is rebuilt
as requirement rows over synthetic file names, scored with the real compiled
security severity classes, and rolled up by observation weight, exactly the
production path minus the database.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.scoring.internals import principle_score_and_grade
from quodeq.core.scoring.mass import RequirementRows, principle_mass
from quodeq.core.scoring.projector_scoring import compute_dimension_score

_FIXTURE = Path(__file__).with_name("benchmark_java_sonnet_security.json")
_BENCHMARK_CEILING = 2.6
_SEVERITIES = ("critical", "major", "minor")


def _rows(principle: dict) -> RequirementRows:
    violations: dict[str, dict[str, str]] = {}
    for req, rule in principle["violations"].items():
        files: dict[str, str] = {}
        for severity in _SEVERITIES:
            for _ in range(rule["filesBySeverity"][severity]):
                files[f"f{len(files)}"] = severity
        violations[req] = files
    compliance = {
        req: frozenset(f"f{i}" for i in range(count))
        for req, count in principle["complianceFiles"].items()
    }
    return RequirementRows(violations=violations, compliance=compliance)


def _dimension_score() -> dict:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    grades = []
    for name, principle in sorted(data["principles"].items()):
        mass = principle_mass(_rows(principle), data["sourceFileCount"])
        score, grade = principle_score_and_grade(mass)
        grades.append({"principle_id": name, "score": score, "grade": grade,
                       "observation": mass.observation, "confidence": None})
    return compute_dimension_score(dimension="security", principle_grades=grades)


def test_benchmark_java_security_grades_at_or_below_the_benchmark_ceiling() -> None:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    out = _dimension_score()
    assert out["score"] <= _BENCHMARK_CEILING
    assert out["score"] < data["storedOverallScore"]
