"""Severity aggregation and totals calculation."""

from __future__ import annotations

from quodeq.core.types import Finding, SeverityTally, Totals

SEVERITIES = {"critical", "major", "minor", "unknown"}


def build_totals(violations: list[Finding], compliance: list[Finding]) -> Totals:
    """Aggregate violation and compliance counts grouped by severity.

    Example::

        build_totals([Finding(severity="major")], [Finding(severity="minor")])
    """
    severity: dict[str, int] = {k: 0 for k in SEVERITIES}
    for entry in violations:
        key = entry.severity or "unknown"
        if key not in SEVERITIES:
            key = "unknown"
        severity[key] += 1
    return Totals(
        violation_count=len(violations),
        compliance_count=len(compliance),
        severity=SeverityTally(
            critical=severity["critical"],
            major=severity["major"],
            minor=severity["minor"],
            unknown=severity["unknown"],
        ),
    )
