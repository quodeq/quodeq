"""Enricher builder shared by the test_finding_enricher* siblings."""
from __future__ import annotations

from quodeq.analysis.mcp.enricher import CompiledContext, FindingEnricher


def _enricher(**ctx_kwargs) -> FindingEnricher:
    return FindingEnricher(CompiledContext(**ctx_kwargs))
