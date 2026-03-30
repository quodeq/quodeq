"""Evidence model — dataclasses for judgments, principles, and evaluation output."""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_WEIGHT = "Medium (x2)"
_HIGH_CONFIDENCE_THRESHOLD = 10  # minimum total instances for "high" confidence
_MEDIUM_CONFIDENCE_THRESHOLD = 5  # minimum total instances for "medium" confidence
_LOW_CONF_MAJORITY_DIVISOR = 2  # denominator for "low confidence majority" threshold
PERCENT_SCALE = 100


def compute_coverage_pct(files_read: int, source_file_count: int) -> float:
    """Return coverage percentage, or 0.0 when there are no source files."""
    if source_file_count > 0:
        return round(files_read / source_file_count * PERCENT_SCALE, 1)
    return 0.0


@dataclass
class Judgment:
    """One LLM judgment per finding."""
    practice_id: str
    file: str = ""
    line: int = 0
    snippet: str = ""
    verdict: str = "violation"  # violation | compliance | dismissed
    severity: str = "medium"
    reason: str = ""
    dimension: str = ""
    req: str | None = None
    req_refs: list[dict] | None = None
    violation_type: str = ""
    title: str = ""
    context: str = ""


@dataclass
class PrincipleEvidence:
    """Aggregated evidence for a single practice/principle."""
    practice_id: str
    display_name: str
    dimension: str
    severity: str
    weight: str = DEFAULT_WEIGHT
    violations: list[dict] = field(default_factory=list)
    compliance: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def compute_metrics(self, scale_multiplier: int = 1) -> None:
        """Calculate compliance percentage and confidence level from violation/compliance counts."""
        high_threshold = _HIGH_CONFIDENCE_THRESHOLD * scale_multiplier
        medium_threshold = _MEDIUM_CONFIDENCE_THRESHOLD * scale_multiplier

        n_violations = len(self.violations)
        n_compliance = len(self.compliance)
        total = n_violations + n_compliance
        pct = round(n_compliance / total * PERCENT_SCALE, 1) if total > 0 else 0.0

        if total >= high_threshold:
            confidence = "high"
        elif total >= medium_threshold:
            confidence = "medium"
        else:
            confidence = "low"

        self.metrics = {
            "total_instances": total,
            "compliant": n_compliance,
            "violating": n_violations,
            "compliance_percentage": pct,
            "confidence_level": confidence,
            "is_balanced": n_violations > 0 and n_compliance > 0,
        }


@dataclass
class Evidence:
    """Complete evaluation output for one run."""
    repository: str
    language: str
    date: str
    source_file_count: int
    files_read: int
    coverage_pct: float
    principles: dict[str, PrincipleEvidence] = field(default_factory=dict)
    dismissed_count: int = 0
    meta: dict = field(default_factory=dict)
    module: str = ""

    def summary(self) -> dict:
        """Return an aggregate summary of findings, confidence, and balance across all principles."""
        total = sum(p.metrics.get("total_instances", 0) for p in self.principles.values())
        low_conf = [k for k, p in self.principles.items() if p.metrics.get("confidence_level") == "low"]
        unbalanced = [k for k, p in self.principles.items() if not p.metrics.get("is_balanced", True)]
        return {
            "total_findings": total,
            "principles_count": len(self.principles),
            "low_confidence_principles": low_conf,
            "unbalanced_principles": unbalanced,
            "overall_confidence": (
                "low" if len(low_conf) > len(self.principles) / _LOW_CONF_MAJORITY_DIVISOR
                else "medium" if low_conf
                else "high"
            ),
            "dismissed_count": self.dismissed_count,
        }

    def to_evidence_dict(self) -> dict:
        """Convert to the dict shape that run_scoring() expects."""
        principles = {}
        for key, pe in self.principles.items():
            principles[key] = {
                "display_name": pe.display_name,
                "weight": pe.weight,
                "violations": pe.violations,
                "compliance": pe.compliance,
                "metrics": pe.metrics,
            }
        result = {
            "repository": self.repository,
            "discipline": self.language.title(),
            "date": self.date,
            "source_file_count": self.source_file_count,
            "files_read": self.files_read,
            "coverage_pct": self.coverage_pct,
            "meta": self.meta,
            "principles": principles,
            "evidence_summary": self.summary(),
        }
        if self.module:
            result["module"] = self.module
        return result
