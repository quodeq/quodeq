"""FindingEnricher keeps a bounded, most-recently-used source cache."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.mcp.enricher import CompiledContext, FindingEnricher

_DISTINCT_FILES = 600


def test_source_cache_evicts_the_least_recently_read_file():
    reads: list[Path] = []

    def reader(path: Path) -> str:
        reads.append(path)
        return "text"

    enricher = FindingEnricher(CompiledContext(), file_reader=reader)
    paths = [Path(f"f{i}.py") for i in range(_DISTINCT_FILES)]
    for path in paths:
        enricher._read_file(path)
    enricher._read_file(paths[-1])  # recent: still cached
    enricher._read_file(paths[0])   # oldest: evicted, read again

    assert reads.count(paths[-1]) == 1
    assert reads.count(paths[0]) == 2
