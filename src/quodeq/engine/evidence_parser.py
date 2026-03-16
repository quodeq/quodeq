"""Re-export for backward compatibility — moved to quodeq.core.evidence.parser."""
from quodeq.core.evidence.parser import (  # noqa: F401
    build_req_refs_lookup,
    EvidenceContext,
    resolve_llm_refs,
    parse_jsonl_to_evidence,
)
