"""Constants shared across quodeq.config modules."""
from __future__ import annotations

# lru_cache bound for the dependency-manifest parsers (_dependency_parsers.py,
# _dependency_parsers_compiled.py, _dependency_parsers_python.py): each
# manifest text is memoized once, not once per discipline rule that probes it.
PARSE_CACHE_MAX = 64
