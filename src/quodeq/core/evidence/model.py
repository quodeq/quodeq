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


_VALID_VERDICTS = frozenset({"violation", "compliance", "dismissed"})
_VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low", "minor"})


@dataclass
class Judgment:
    """One LLM judgment per finding."""
    practice_id: str
    file: str = ""
    line: int = 0
    end_line: int = 0
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
    scope: str = ""
    # 0-100 confidence score the scanner attaches to this finding. 100 means
    # "no reason to doubt." Subsequent slices of the context-enricher plan
    # populate values < 100 to downweight known false-positive patterns.
    confidence: int = 100

    def __post_init__(self) -> None:
        if not self.practice_id:
            raise ValueError("Judgment requires a practice_id")

    def is_violation(self) -> bool:
        return self.verdict == "violation"

    def is_compliance(self) -> bool:
        return self.verdict == "compliance"


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

    def __post_init__(self) -> None:
        if not self.practice_id:
            raise ValueError("PrincipleEvidence requires a practice_id")

    def add_violations(self, items: list[dict]) -> None:
        """Append violation findings and recompute metrics."""
        self.violations.extend(items)
        self.compute_metrics()

    def add_compliance(self, items: list[dict]) -> None:
        """Append compliance findings and recompute metrics."""
        self.compliance.extend(items)
        self.compute_metrics()

    def merge_findings(self, other: PrincipleEvidence) -> None:
        """Merge another PrincipleEvidence's findings into this one."""
        self.violations.extend(other.violations)
        self.compliance.extend(other.compliance)
        self.compute_metrics()

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
        """Convert to the dict shape that run_scoring() expects.

        Delegates to the module-level :func:`evidence_to_scoring_dict`
        so that serialization logic is not coupled to the entity itself.
        """
        return evidence_to_scoring_dict(self)


def evidence_to_scoring_dict(evidence: Evidence) -> dict:
    """Serialize an Evidence instance into the dict shape that run_scoring() expects.

    Kept as a standalone function so adapter/engine layers can call it
    without depending on the entity method.
    """
    principles = {}
    for key, pe in evidence.principles.items():
        principles[key] = {
            "display_name": pe.display_name,
            "weight": pe.weight,
            "violations": pe.violations,
            "compliance": pe.compliance,
            "metrics": pe.metrics,
        }
    result = {
        "repository": evidence.repository,
        "discipline": evidence.language.title(),
        "date": evidence.date,
        "source_file_count": evidence.source_file_count,
        "files_read": evidence.files_read,
        "coverage_pct": evidence.coverage_pct,
        "meta": evidence.meta,
        "principles": principles,
        "evidence_summary": evidence.summary(),
    }
    if evidence.module:
        result["module"] = evidence.module
    return result
