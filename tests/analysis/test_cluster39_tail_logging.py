"""Cluster 39: analysis silent fallbacks now leave a debug trace."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from quodeq.analysis import _pipeline
from quodeq.analysis.cache import _key_provenance, dimension_helpers
from quodeq.analysis.cache._persist_watcher import CachePersistProvenance
from quodeq.analysis.cache.dimension_helpers import CacheEntryTarget


def test_build_cache_entry_logs_when_content_hash_is_unavailable(monkeypatch, tmp_path) -> None:
    # Both write paths hash through _key_provenance._content_hash_for.
    monkeypatch.setattr(_key_provenance, "hash_file", lambda path: None)
    # _build_cache_entry_for_file reads only config.src and config.language.
    config = SimpleNamespace(src=tmp_path, language="python")
    target = CacheEntryTarget(file_path="a.py", key="cache-key", model_id="model", version="v1")
    provenance = CachePersistProvenance(
        standards_hash="s", params_hash="p", effective_params={}, prompts_hash="q",
    )
    with patch.object(dimension_helpers._logger, "debug") as debug:
        entry = dimension_helpers._build_cache_entry_for_file(config, "security", target, {}, provenance)
    assert entry.file_content_hash == ""
    assert debug.called
    assert "content hash unavailable" in debug.call_args.args[0]
    assert debug.call_args.args[1] == "a.py"


def test_persist_dim_estimates_failure_logs_and_returns(monkeypatch, tmp_path) -> None:
    def _boom(*_a, **_k):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(_pipeline, "compute_dim_estimates", _boom)
    messages: list[str] = []
    monkeypatch.setattr(_pipeline.SHARED_LOG, "debug", messages.append)
    # _persist_dim_estimates reads config.work_dir before delegating; the
    # delegate is mocked, so a namespace with work_dir is a sufficient config.
    _pipeline._persist_dim_estimates(SimpleNamespace(work_dir=tmp_path), ["security"])
    assert messages
    assert "dim estimates skipped" in messages[0]
