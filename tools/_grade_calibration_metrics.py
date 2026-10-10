"""Scoring and yardsticks for the grade calibration harness.

Every score goes through the production grade functions; this module only
re-feeds stored findings into them and measures the spread of the results.
"""
from __future__ import annotations

import itertools
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from _grade_calibration_load import Report  # noqa: E402
from quodeq.core.scoring.internals import principle_score_and_grade, score_to_grade_label  # noqa: E402
from quodeq.core.scoring.mass import principle_mass, requirement_rows  # noqa: E402
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams  # noqa: E402
from quodeq.core.scoring.projector_scoring import compute_dimension_score, compute_run_score  # noqa: E402
from quodeq.core.scoring.report_grades import NUMERIC_GRADE_ORDER  # noqa: E402

MODEL_WINDOW_DAYS = 45
NAME_WIDTH = 12
RUN_WIDTH = 8
P90 = 0.9
PERCENT = 100
DIGITS = 3
BENCHMARK_PREFIX = "benchmark"
BENCHMARK_DIMENSION = "security"
NO_MODEL = "None"
GRADES = tuple(reversed(NUMERIC_GRADE_ORDER))


def short(name: str) -> str:
    """A project name cut to the width the harness prints."""
    return name[:NAME_WIDTH]


def score_report(
    report: Report, params: ScoringParams, *, drop: frozenset[str] = frozenset(),
) -> float | None:
    """Dimension score of a stored report under *params*, optionally with the *drop* rules removed."""
    graded = []
    for violations, compliance in report.principles.values():
        kept = [v for v in violations if v["req"] not in drop]
        if not kept and not compliance:
            continue
        mass = principle_mass(requirement_rows(kept, compliance), report.files, params=params)
        score, _grade = principle_score_and_grade(mass, params=params)
        graded.append({"score": score, "observation": mass.observation, "confidence": None})
    return compute_dimension_score(dimension=report.dimension, principle_grades=graded, params=params)["score"]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, DIGITS)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _days_apart(a: str, b: str) -> int | None:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except ValueError:
        return None


def _real_model(report: Report) -> bool:
    return bool(report.model) and NO_MODEL not in report.model


def _dated(report: Report) -> bool:
    try:
        date.fromisoformat(report.date)
    except ValueError:
        return False
    return True


def _latest(pairs: list[tuple[Report, float]]) -> dict[tuple[str, str], tuple[Report, float]]:
    latest: dict[tuple[str, str], tuple[Report, float]] = {}
    for report, score in pairs:
        key = (report.project, report.dimension)
        if key not in latest or report.date > latest[key][0].date:
            latest[key] = (report, score)
    return latest


def _model_gaps(pairs: list[tuple[Report, float]]) -> list[float]:
    """|score gap| between each project and dimension's latest runs of two models within the window."""
    groups: dict[tuple[str, str], dict[str, tuple[Report, float]]] = {}
    for report, score in pairs:
        if not (_real_model(report) and _dated(report)):
            continue
        slot = groups.setdefault((report.project, report.dimension), {})
        if report.model not in slot or report.date > slot[report.model][0].date:
            slot[report.model] = (report, score)
    gaps = []
    for latest in groups.values():
        for (a, sa), (b, sb) in itertools.combinations(latest.values(), 2):
            days = _days_apart(a.date, b.date)
            if days is not None and days <= MODEL_WINDOW_DAYS:
                gaps.append(abs(sa - sb))
    return gaps


def _temporal_deltas(pairs: list[tuple[Report, float]]) -> list[float]:
    """|score change| between consecutive runs of the same model on one project and dimension."""
    series: dict[tuple[str, str, str], list[tuple[Report, float]]] = {}
    for report, score in pairs:
        if _real_model(report) and _dated(report):
            series.setdefault((report.project, report.dimension, report.model), []).append((report, score))
    deltas = []
    for runs in series.values():
        runs.sort(key=lambda rs: rs[0].date)
        deltas.extend(abs(b[1] - a[1]) for a, b in zip(runs, runs[1:]))
    return deltas


def _benchmark(pairs: list[tuple[Report, float]]) -> tuple[list[float], list[float]]:
    """Scores of the benchmark security runs and the gaps between runs of one benchmark."""
    by_project: dict[str, list[float]] = {}
    for report, score in pairs:
        if report.project.lower().startswith(BENCHMARK_PREFIX) and report.dimension == BENCHMARK_DIMENSION:
            by_project.setdefault(report.project, []).append(score)
    scores = [s for group in by_project.values() for s in group]
    gaps = [abs(a - b) for group in by_project.values() for a, b in itertools.combinations(group, 2)]
    return scores, gaps


def _grade_shares(scores: list[float], params: ScoringParams) -> dict[str, float]:
    counts = Counter(score_to_grade_label(s, params=params) for s in scores)
    return {label: round(PERCENT * counts[label] / len(scores), 1) if scores else 0.0 for label in GRADES}


def motion_rows(
    reports: list[Report], scores: list[float | None], motion: tuple[str, list[str]],
    *, params: ScoringParams,
) -> list[dict]:
    """Score change when every violation under the listed rules is removed, per report of the named run."""
    run_prefix, rules = motion
    rows = []
    for report, before in zip(reports, scores):
        if before is None or not report.run.startswith(run_prefix):
            continue
        after = score_report(report, params, drop=frozenset(rules))
        rows.append({
            "project": short(report.project), "dimension": report.dimension, "run": report.run[:RUN_WIDTH],
            "before": before, "after": after, "delta": None if after is None else round(after - before, 1),
        })
    return rows


def yardsticks(
    reports: list[Report], scores: list[float | None], *, params: ScoringParams = DEFAULT_PARAMS,
    motion: tuple[str, list[str]] | None = None,
) -> dict:
    """The calibration measures of one set of scores, aligned with *reports* (``None`` scores are skipped)."""
    pairs = [(r, s) for r, s in zip(reports, scores) if s is not None]
    values = [s for _r, s in pairs]
    bench, bench_gaps = _benchmark(pairs)
    gaps = _model_gaps(pairs)
    deltas = sorted(_temporal_deltas(pairs))
    between = statistics.pstdev([s for _r, s in _latest(pairs).values()]) if pairs else 0.0
    return {
        "reports": len(pairs),
        "mean_score": _round(_mean(values)),
        "benchmark_range": [min(bench), max(bench)] if bench else None,
        "benchmark_deviation": _round(_mean(bench_gaps)),
        "model_pairs": len(gaps),
        "model_deviation": _round(_mean(gaps)),
        "signal_to_noise": _round(between / statistics.mean(gaps)) if gaps and statistics.mean(gaps) > 0 else None,
        "grade_shares": _grade_shares(values, params),
        "temporal_pairs": len(deltas),
        "temporal_mean_delta": _round(_mean(deltas)),
        "temporal_p90": _round(deltas[int(P90 * len(deltas))]) if deltas else None,
        "motion": motion_rows(reports, scores, motion, params=params) if motion else [],
    }


def label_rows(
    reports: list[Report], scores: list[float | None], labels: dict[str, str], params: ScoringParams,
) -> list[dict]:
    """Per labelled project, the band of its latest run score against the expected one."""
    pairs = [(r, s) for r, s in zip(reports, scores) if s is not None]
    rows = []
    for name, expected in sorted(labels.items()):
        latest = [{"dimension": r.dimension, "score": s} for (p, _d), (r, s) in _latest(pairs).items() if p == name]
        run = compute_run_score(latest, params)
        rows.append({"project": short(name), "score": run["score"], "band": run["grade"], "expected": expected, "match": run["grade"] == expected})
    return rows
