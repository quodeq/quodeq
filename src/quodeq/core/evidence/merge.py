"""Evidence merging — combines per-dimension Evidence objects into one."""
from __future__ import annotations

from quodeq.core.evidence.model import Evidence, PrincipleEvidence, PERCENT_SCALE


def merge_evidence(evidence_list: list[Evidence], source_file_count: int, src: str, plugin_id: str) -> Evidence:
    """Merge per-dimension Evidence objects into a single Evidence."""
    merged_principles: dict[str, PrincipleEvidence] = {}
    total_files_read = 0
    total_dismissed = 0

    for ev in evidence_list:
        total_files_read = max(total_files_read, ev.files_read)
        total_dismissed += ev.dismissed_count
        for pid, pe in ev.principles.items():
            if pid in merged_principles:
                existing = merged_principles[pid]
                existing.violations.extend(pe.violations)
                existing.compliance.extend(pe.compliance)
                existing.compute_metrics()
            else:
                merged_principles[pid] = pe

    coverage_pct = (
        round(total_files_read / source_file_count * PERCENT_SCALE, 1)
        if source_file_count > 0
        else 0.0
    )

    merged = Evidence(
        repository=src,
        plugin_id=plugin_id,
        date=evidence_list[0].date if evidence_list else "",
        source_file_count=source_file_count,
        files_read=total_files_read,
        coverage_pct=coverage_pct,
        principles=merged_principles,
        dismissed_count=total_dismissed,
    )
    if evidence_list:
        merged.plugin_name = evidence_list[0].plugin_name
    return merged
