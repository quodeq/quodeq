"""Evidence parsing — JSONL → ``Evidence``.

The V2 dimension runner uses ``parse_evidence_from_jsonl`` to build
the final ``Evidence`` object once cache hits and dispatch results
have all been merged into the dimension's ``<dim>_evidence.jsonl``.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.config.evidence_env import cwe_url_template
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.data.fs.standards_loader import read_req_to_principle_map


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
        req_map_reader=read_req_to_principle_map,
        cwe_url_template=cwe_url_template(),
    )
