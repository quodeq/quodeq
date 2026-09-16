"""Canonical violation-type taxonomy (spec 2026-09-15). Pure: no IO, no logging."""
from quodeq.core.taxonomy._fold import fold
from quodeq.core.taxonomy.extract import TaxonomyError, extract_taxonomy
from quodeq.core.taxonomy.model import EMPTY_TAXONOMY, OTHER, RequirementTypes, Taxonomy
from quodeq.core.taxonomy.normalize import canonicalize

__all__ = [
    "EMPTY_TAXONOMY", "OTHER", "RequirementTypes", "Taxonomy", "TaxonomyError",
    "canonicalize", "extract_taxonomy", "fold",
]
