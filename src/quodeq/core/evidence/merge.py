"""Evidence merging — combines per-dimension Evidence objects into one."""
from __future__ import annotations

from quodeq.core.evidence.model import Evidence, PrincipleEvidence, compute_coverage_pct


def merge_evidence(
    evidence_list: list[Evidence], source_file_count: int, src: str, language: str,
    module: str = "",
) -> Evidence:
    """Merge per-dimension Evidence objects into a single Evidence."""
    merged_principles: dict[str, PrincipleEvidence] = {}
    total_files_read = 0
    total_dismissed = 0

    for ev in evidence_list:
        total_files_read = max(total_files_read, ev.files_read)
        total_dismissed += ev.dismissed_count
        for pid, pe in ev.principles.items():
            if pid in merged_principles:
                merged_principles[pid].merge_findings(pe)
            else:
                merged_principles[pid] = pe

    # merge_findings recomputes metrics with default thresholds; redo
    # the pass with the merged source_file_count so small-project
    # confidence scaling survives the merge.
    for pe in merged_principles.values():
        pe.compute_metrics(source_file_count=source_file_count)

    coverage_pct = compute_coverage_pct(total_files_read, source_file_count)

    # Inherit module from the first evidence object if not explicitly provided
    if not module and evidence_list:
        module = evidence_list[0].module

    merged = Evidence(
        repository=src,
        language=language,
        date=evidence_list[0].date if evidence_list else "",
        source_file_count=source_file_count,
        files_read=total_files_read,
        coverage_pct=coverage_pct,
        principles=merged_principles,
        dismissed_count=total_dismissed,
        module=module,
    )
    return merged
