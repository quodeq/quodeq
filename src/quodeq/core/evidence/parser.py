"""Evidence parser -- converts extracted JSONL lines into V2 Evidence model."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.core.evidence._jsonl import judgment_to_dict, parse_jsonl_line, read_judgments
from quodeq.core.evidence._options import EvidenceParseOptions
from quodeq.core.evidence._refs import enrich_judgment, resolve_llm_refs
from quodeq.core.utils.io import open_text
from quodeq.core.events.models import Judgment
from quodeq.core.evidence._req_mapping import _GroupedJudgments, _group_judgments
from quodeq.core.evidence.model import Evidence, PrincipleEvidence, compute_coverage_pct

# Re-export for backward compatibility (external code imports these from parser)
__all__ = ["resolve_llm_refs", "EvidenceContext", "EvidenceParseOptions",
           "parse_jsonl_to_evidence", "parse_jsonl_to_evidence_by_dimension"]

_NO_OPTIONS = EvidenceParseOptions()

# Preserve private-name aliases used by tests
_parse_jsonl_line = parse_jsonl_line


@dataclass
class EvidenceContext:
    """Metadata needed to construct an Evidence object from parsed JSONL."""
    language: str
    repository: str
    date_str: str
    source_file_count: int
    files_read: int
    module: str = ""
    exit_reason: str | None = None


def _build_principles(
    grouped: _GroupedJudgments, dimension_name: str, source_file_count: int = 0,
) -> dict[str, PrincipleEvidence]:
    """Build scored PrincipleEvidence entries from grouped judgments."""
    all_keys = set(grouped.violations.keys()) | set(grouped.compliance.keys())
    principles: dict[str, PrincipleEvidence] = {}
    for sc in sorted(all_keys):
        pe = PrincipleEvidence(
            practice_id=sc, display_name=sc, dimension=dimension_name,
            severity=grouped.severity.get(sc, "medium"),
            violations=[judgment_to_dict(j) for j in grouped.violations.get(sc, [])],
            compliance=[judgment_to_dict(j) for j in grouped.compliance.get(sc, [])],
        )
        pe.compute_metrics(source_file_count=source_file_count)
        principles[sc] = pe
    return principles


def _build_evidence(
    context: EvidenceContext, principles: dict[str, PrincipleEvidence],
    quarantined: int = 0,
) -> Evidence:
    """Create an Evidence object from context and principles."""
    return Evidence(
        repository=context.repository, language=context.language, date=context.date_str,
        source_file_count=context.source_file_count, files_read=context.files_read,
        coverage_pct=compute_coverage_pct(context.files_read, context.source_file_count),
        principles=principles, dismissed_count=0, quarantined_count=quarantined,
        module=context.module, exit_reason=context.exit_reason,
    )


def _read_by_dimension(
    jsonl_file: Path, options: EvidenceParseOptions,
) -> dict[str, list[Judgment]]:
    """Enriched judgments keyed by dimension, grouped while streaming the file."""
    by_dim: dict[str, list[Judgment]] = {}
    opener = options.open_fn or open_text
    with opener(jsonl_file) as jf:
        req_refs_cache: dict[str, dict[str, list[dict]]] = {}
        for line in jf:
            result = parse_jsonl_line(line, on_malformed_line=options.on_malformed_line)
            if result is not None:
                j, llm_refs = result
                j = enrich_judgment(j, llm_refs, req_refs_cache, options)
                by_dim.setdefault(j.dimension or "unknown", []).append(j)
    return by_dim


def parse_jsonl_to_evidence_by_dimension(
    jsonl_file: Path, context: EvidenceContext,
    options: EvidenceParseOptions = _NO_OPTIONS,
) -> dict[str, Evidence]:
    """Parse a multi-dimension JSONL file into per-dimension Evidence objects.

    Groups judgments by dimension incrementally during parsing to avoid
    holding the full flat list in memory.
    """
    if not jsonl_file.exists():
        return {}
    by_dim = _read_by_dimension(jsonl_file, options)
    if not by_dim:
        return {}
    result: dict[str, Evidence] = {}
    all_quarantined = []
    for dim, dj in by_dim.items():
        grouped = _group_judgments(dj, dimension=dim, evaluators_dir=options.evaluators_dir,
                                   compiled_dir=options.compiled_dir,
                                   req_map_reader=options.req_map_reader)
        all_quarantined.extend(grouped.quarantined_findings)
        result[dim] = _build_evidence(
            context, _build_principles(grouped, dim, context.source_file_count),
            grouped.quarantined,
        )
    if options.on_quarantine is not None and all_quarantined:
        options.on_quarantine(all_quarantined)
    return result


def parse_jsonl_to_evidence(
    jsonl_file: Path, context: EvidenceContext,
    options: EvidenceParseOptions = _NO_OPTIONS,
) -> Evidence:
    """Parse extracted JSONL file into a complete Evidence object."""
    # NOTE: read_judgments materializes all judgments into a list.  This is
    # intentional because _group_judgments needs random access and the caller
    # indexes judgments[0] for the dimension name.  For streaming scenarios use
    # parse_jsonl_to_evidence_by_dimension which groups incrementally.
    judgments = read_judgments(jsonl_file, options)
    dim = judgments[0].dimension if judgments else ""
    grouped = _group_judgments(judgments, dimension=dim, evaluators_dir=options.evaluators_dir,
                               compiled_dir=options.compiled_dir,
                               req_map_reader=options.req_map_reader)
    if options.on_quarantine is not None and grouped.quarantined_findings:
        options.on_quarantine(grouped.quarantined_findings)
    return _build_evidence(
        context, _build_principles(grouped, dim, context.source_file_count),
        grouped.quarantined,
    )
