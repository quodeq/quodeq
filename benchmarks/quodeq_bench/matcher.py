"""Match quodeq findings against ground-truth labels."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quodeq_bench.evidence import Finding, parse_cwe_refs
from quodeq_bench.models import CaseTruth, Label

LINE_WINDOW = 5


def normalize_path(path: str) -> str:
    text = path.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


@dataclass(frozen=True)
class CaseMatch:
    total_labels: int
    matched_labels: int
    matched_findings: int
    fp_findings: int
    duplicates: int
    severity_agreements: int


def _line_matches(label: Label, finding: Finding) -> bool:
    lo = label.line - LINE_WINDOW
    hi = (label.end_line or label.line) + LINE_WINDOW
    return lo <= finding.line <= hi


def _class_matches(label: Label, finding: Finding) -> bool:
    if label.cwes and set(label.cwes) & set(parse_cwe_refs(finding.refs)):
        return True
    if label.reqs and finding.req in label.reqs:
        return True
    return False


def _matches(label: Label, finding: Finding) -> bool:
    return (
        label.dimension == finding.dimension
        and normalize_path(label.file) == normalize_path(finding.file)
        and _line_matches(label, finding)
        and _class_matches(label, finding)
    )


def match_case(truth: CaseTruth, findings: Sequence[Finding]) -> dict[str, CaseMatch]:
    clean = {normalize_path(f) for f in truth.clean_files}
    hits: dict[int, list[Finding]] = {}
    fp_by_dim: dict[str, int] = {}

    for finding in findings:
        target: int | None = None
        for idx, label in enumerate(truth.labels):
            if _matches(label, finding):
                target = idx
                break
        if target is not None:
            hits.setdefault(target, []).append(finding)
        elif truth.exhaustive or normalize_path(finding.file) in clean:
            fp_by_dim[finding.dimension] = fp_by_dim.get(finding.dimension, 0) + 1

    dims = {label.dimension for label in truth.labels} | set(fp_by_dim)
    result: dict[str, CaseMatch] = {}
    for dim in dims:
        labels = [
            (i, label) for i, label in enumerate(truth.labels) if label.dimension == dim
        ]
        matched = [(i, label) for i, label in labels if i in hits]
        matched_findings = sum(len(hits[i]) for i, _ in matched)
        agreements = sum(
            1 for i, label in matched if hits[i][0].severity == label.severity
        )
        result[dim] = CaseMatch(
            total_labels=len(labels),
            matched_labels=len(matched),
            matched_findings=matched_findings,
            fp_findings=fp_by_dim.get(dim, 0),
            duplicates=matched_findings - len(matched),
            severity_agreements=agreements,
        )
    return result
