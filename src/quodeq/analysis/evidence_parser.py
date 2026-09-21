"""Evidence parsing — JSONL → ``Evidence``.

The V2 dimension runner uses ``parse_evidence_from_jsonl`` to build
the final ``Evidence`` object once cache hits and dispatch results
have all been merged into the dimension's ``<dim>_evidence.jsonl``.

``evidence_parse_options`` and ``parse_evidence_file`` are the shared
pieces: the per-dimension runner, the single-dimension step and the
consolidated pass all parse with the same readers and log sinks.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.run_types import RunConfig, _AnalysisContext
from quodeq.config.evidence_env import cwe_url_template
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import (
    EvidenceContext, EvidenceParseOptions, parse_jsonl_to_evidence)
from quodeq.data.fs.standards_loader import load_compiled_refs, read_req_to_principle_map
from quodeq.shared.log_sink import log_malformed_jsonl_line, log_quarantined_findings


def evidence_parse_options(config: RunConfig, compiled_dir: Path | None) -> EvidenceParseOptions:
    """Production readers and log sinks for an evidence parse."""
    return EvidenceParseOptions(
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
        req_map_reader=read_req_to_principle_map,
        refs_reader=load_compiled_refs,
        cwe_url_template=cwe_url_template(),
        on_quarantine=log_quarantined_findings,
        on_malformed_line=log_malformed_jsonl_line,
    )


def parse_evidence_file(
    config: RunConfig, ctx: _AnalysisContext,
    jsonl_file: Path, files_read: int,
) -> Evidence:
    """Parse *jsonl_file* into Evidence, with no existence guard.

    The dimension name comes from the judgments in the file, not from the
    caller. Callers that need "no evidence yet" to read as None check the
    file first (see :func:`parse_evidence_from_jsonl`).
    """
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    return parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            language=config.language, repository=str(config.src),
            date_str=ctx.date_str, source_file_count=config.source_file_count,
            files_read=files_read, module=config.target.name if config.target else "",
        ),
        evidence_parse_options(config, compiled_dir),
    )


def parse_evidence_from_jsonl(
    config: RunConfig, ctx: _AnalysisContext,
    jsonl_file: Path, files_read: int,
) -> Evidence | None:
    """Parse a JSONL file into Evidence, or None when the file holds nothing.

    The dimension name comes from the judgments in *jsonl_file*, not from the
    caller.
    """
    # File existence check is necessary — evidence may not exist yet for new dimensions.
    if not jsonl_file.exists() or jsonl_file.stat().st_size == 0:
        return None
    return parse_evidence_file(config, ctx, jsonl_file, files_read)
