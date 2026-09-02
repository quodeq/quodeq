"""Clean-scan honoring — classify_files_via_cache(bypass_reads=True).

Split from test_clean_scan_honor.py: every file goes to misses regardless
of cache state; the miss_keys map is still populated so
persist_dispatch_results can write entries. Shared scaffolding lives in
tests/analysis/cache/_clean_scan_honor_fixtures.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.cache import LocalFileBackend, classify_files_via_cache

from tests.analysis.cache._clean_scan_honor_fixtures import (  # noqa: F401 -- cache is a pytest fixture
    _populate_cache,
    _setup,
    cache,
)


class TestClassifyBypassReads:
    def test_bypass_reads_all_miss_despite_full_cache(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config, _ = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        _populate_cache(cache, config, "security", ["a.py", "b.py"])

        result = classify_files_via_cache(
            config, "security", ["a.py", "b.py"], cache,
            bypass_reads=True,
        )
        assert result.cached_findings == []
        assert sorted(result.misses) == ["a.py", "b.py"]
        # miss_keys must still be populated so writeback works.
        assert set(result.miss_keys.keys()) == {"a.py", "b.py"}

    def test_default_reads_normally(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Sanity: bypass_reads defaults to False and existing behaviour holds."""
        config, _ = _setup(tmp_path, {"a.py": "x"})
        _populate_cache(cache, config, "security", ["a.py"])

        result = classify_files_via_cache(config, "security", ["a.py"], cache)
        assert result.misses == []
        assert len(result.cached_findings) == 1


# Removed TestOrchestratorFastPathHonorsCleanScan: the orchestrator-level
# _try_v2_full_hit no longer exists. After B6 the orchestrator delegates
# to DimensionRunner.run which routes through process_dimension_with_cache,
# and clean-scan honoring is verified at that layer (TestDispatchBypassesCacheOnCleanScan
# in test_clean_scan_honor_dispatch.py).
