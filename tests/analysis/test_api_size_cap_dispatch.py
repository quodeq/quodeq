"""The API-provider file-size cap must be enforced at enumeration, not
silently at dispatch (the perpetual-97%-coverage bug).

Bug: ``_gather_api_source_files`` dropped files over ``QUODEQ_MAX_API_FILE_SIZE``
*after* taking them from the queue, without writing any ``file_done`` marker.
The files never entered the cache, so every incremental run re-counted them as
misses, re-queued them, and re-skipped them. The same ~3% of files haunted
every run and dim coverage never reached 100%.

The fix has one rule: the queue builder / estimates (``list_source_files``)
and the dispatch-time worker must share ONE dispatchability predicate
(``quodeq.analysis.dispatch_policy``), and any file the worker still drops
must leave an explicit ``skipped`` marker behind. The worker-side markers
and batching live in test_api_size_cap_dispatch_worker.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quodeq.analysis._dim_estimates import compute_dim_estimates
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.dispatch_policy import DispatchPolicy
from quodeq.analysis.subagents.source_files import list_source_files

from ._api_size_cap_dispatch_helpers import CAP, _TEST_PROVIDER, _make_config, _write_repo


class TestEnumerationAppliesCap:
    def test_list_source_files_excludes_oversized_for_api_provider(
        self, tmp_path: Path, api_provider,
    ):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        files, _ext, excluded = list_source_files(config, "security")

        assert files == ["small.py"]
        assert excluded == ["big.py"]

    def test_list_source_files_keeps_oversized_for_cli_provider(
        self, tmp_path: Path, cli_provider,
    ):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        files, _ext, excluded = list_source_files(config, "security")

        assert sorted(files) == ["big.py", "small.py"]
        assert excluded == []

    def test_dim_estimates_totals_exclude_oversized(self, tmp_path: Path, api_provider):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        result = compute_dim_estimates(config, ["security"])

        # The oversized file can never be dispatched, so it must not be part
        # of count/total (the coverage denominator) -- it is reported apart.
        assert result["security"]["count"] == 1
        assert result["security"]["total"] == 1
        assert result["security"]["excluded"] == 1

    def test_dim_estimates_incremental_never_requeues_excluded(
        self, tmp_path: Path, api_provider,
    ):
        """The original symptom: with a warm cache for every dispatchable
        file, an incremental run must have NOTHING left to dispatch."""
        from quodeq.analysis.cache import CacheEntry, build_cache_key_for_file

        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])
        config.options.incremental = True
        cache = LocalFileBackend(root=tmp_path / "cache")
        key = build_cache_key_for_file(config, "small.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1, findings=[],
            files_read=1, file_path="small.py", dimension="security",
            model_id="test-model",
        ))

        with patch(
            "quodeq.analysis._dim_estimates.LocalFileBackend", return_value=cache,
        ):
            result = compute_dim_estimates(config, ["security"])

        assert result["security"]["count"] == 0
        assert result["security"]["cached"] == 1
        assert result["security"]["total"] == 1


class TestCoverageDenominator:
    """``source_file_count`` -- the coverage denominator -- reads the
    RunConfig's DispatchPolicy. No env, no patching, no real files:
    ``stat_size`` is a literal in-memory lookup.
    """

    _SIZES = {"small.py": 10, "big.py": CAP + 1}

    @staticmethod
    def _stat_size(path: Path) -> int:
        return TestCoverageDenominator._SIZES[path.name]

    def test_source_file_count_reflects_api_eligibility(self, tmp_path: Path):
        policy = DispatchPolicy(
            provider_configs={_TEST_PROVIDER: {"type": "api"}},
            ai_cmd=_TEST_PROVIDER, file_size_cap=CAP, stat_size=self._stat_size,
        )
        config = _make_config(tmp_path / "src", ["small.py", "big.py"], dispatch=policy)

        assert config.source_file_count == 1

    def test_source_file_count_unchanged_for_cli_provider(self, tmp_path: Path):
        policy = DispatchPolicy(
            provider_configs={_TEST_PROVIDER: {"type": "cli"}},
            ai_cmd=_TEST_PROVIDER, file_size_cap=CAP, stat_size=self._stat_size,
        )
        config = _make_config(tmp_path / "src", ["small.py", "big.py"], dispatch=policy)

        assert config.source_file_count == 2


class TestDispatchPolicyParity:
    """The queue/denominator divergence-bug guard (the "perpetual 97%"
    coverage bug): ``list_source_files`` (queue/estimates enumeration) and
    ``RunConfig._policy()`` (the coverage denominator) must agree on which
    files are dispatchable for the SAME RunConfig. A future change that lets
    one of these paths resolve a different DispatchPolicy than the other
    reintroduces the bug this module's docstring describes.
    """

    def test_list_source_files_matches_policy_split(self, tmp_path: Path, api_provider):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])
        all_files = config.manifest.source_files

        files, _ext, _excluded = list_source_files(config, "security")
        dispatchable, _excluded2 = config._policy().split_api_dispatchable(config.src, all_files)

        assert files == dispatchable
