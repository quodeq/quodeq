"""Compare a candidate benchmark report against a committed baseline."""

from __future__ import annotations

from dataclasses import dataclass

_GATED_METRICS = ("precision", "recall")


@dataclass(frozen=True)
class Regression:
    dimension: str
    metric: str
    baseline: float
    candidate: float


def compare_reports(
    baseline: dict, candidate: dict, threshold: float = 0.05
) -> list[Regression]:
    if baseline.get("bootstrap"):
        return []
    regressions: list[Regression] = []
    candidate_metrics = candidate.get("metrics", {})
    for dim, base_row in baseline.get("metrics", {}).items():
        cand_row = candidate_metrics.get(dim, {})
        for metric in _GATED_METRICS:
            base_value = float(base_row.get(metric, 0.0))
            cand_value = float(cand_row.get(metric, 0.0))
            if base_value - cand_value > threshold:
                regressions.append(
                    Regression(
                        dimension=dim, metric=metric,
                        baseline=base_value, candidate=cand_value,
                    )
                )
    return regressions
