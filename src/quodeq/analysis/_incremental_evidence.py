"""Evidence parsing — JSONL → ``Evidence``.

Post-V2 (B6.1): the per-dimension fingerprint write
(``save_dimension_fingerprint``) and its supporting helpers are gone.
V2 writes per-file cache entries during dispatch — there is no
fingerprint to persist. This module exists solely to host
``parse_evidence_from_jsonl``, which V2's dimension runner uses.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence


def parse_evidence_from_jsonl(
    config: RunConfig, dimension: str, ctx: _AnalysisContext,
    jsonl_file: Path, files_read: int,
) -> Evidence | None:
    """Parse a JSONL file into Evidence."""
    # File existence check is necessary — evidence may not exist yet for new dimensions.
    if not jsonl_file.exists() or jsonl_file.stat().st_size == 0:
        return None
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    return parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            language=config.language, repository=str(config.src),
            date_str=ctx.date_str, source_file_count=config.source_file_count,
            files_read=files_read, module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )
