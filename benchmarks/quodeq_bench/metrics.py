"""Aggregate match results into per-dimension accuracy metrics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from quodeq_bench.matcher import CaseMatch

_EXTENSIONS = {"python": ".py", "javascript": ".js"}


@dataclass
class DimensionMetrics:
    total_labels: int = 0
    matched_labels: int = 0
    matched_findings: int = 0
    fp: int = 0
    duplicates: int = 0
    severity_agreements: int = 0
    kloc: float = 0.0

    @property
    def recall(self) -> float:
        return self.matched_labels / self.total_labels if self.total_labels else 0.0

    @property
    def precision(self) -> float:
        denom = self.matched_findings + self.fp
        return self.matched_findings / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def severity_agreement(self) -> float:
        return (
            self.severity_agreements / self.matched_labels
            if self.matched_labels
            else 0.0
        )

    @property
    def duplicate_rate(self) -> float:
        return self.duplicates / self.matched_labels if self.matched_labels else 0.0

    @property
    def fp_density(self) -> float:
        return self.fp / self.kloc if self.kloc else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total_labels": self.total_labels,
            "matched_labels": self.matched_labels,
            "matched_findings": self.matched_findings,
            "fp": self.fp,
            "duplicates": self.duplicates,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "severity_agreement": round(self.severity_agreement, 4),
            "duplicate_rate": round(self.duplicate_rate, 4),
            "fp_density": round(self.fp_density, 4),
            "kloc": round(self.kloc, 3),
        }


def aggregate(
    case_matches: Iterable[dict[str, CaseMatch]],
    kloc_per_case: Iterable[float],
) -> dict[str, DimensionMetrics]:
    totals: dict[str, DimensionMetrics] = {}
    total_kloc = 0.0
    for matches, kloc in zip(case_matches, kloc_per_case, strict=True):
        total_kloc += kloc
        for dim, cm in matches.items():
            m = totals.setdefault(dim, DimensionMetrics())
            m.total_labels += cm.total_labels
            m.matched_labels += cm.matched_labels
            m.matched_findings += cm.matched_findings
            m.fp += cm.fp_findings
            m.duplicates += cm.duplicates
            m.severity_agreements += cm.severity_agreements
    for m in totals.values():
        m.kloc = total_kloc
    return totals


def count_kloc(case_dir: Path, language: str) -> float:
    ext = _EXTENSIONS.get(language, ".py")
    lines = 0
    for path in sorted(case_dir.rglob(f"*{ext}")):
        lines += sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return lines / 1000
