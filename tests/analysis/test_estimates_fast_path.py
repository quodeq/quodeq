"""The read-only /estimates path skips work that cannot change its counts.

Prioritization only reorders files, a hit/miss count needs no entry body, and
a file's content hash is the same for every dimension within one request. The
pipeline keeps all three: the dim runner reuses its classification through the
classify stash, and minutes pass between its classifications.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.estimates import compute_dim_estimates
from quodeq.analysis.cache import CacheEntry, LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.fingerprint import hash_file
from quodeq.analysis.subagents import source_files
from tests.analysis.test_dim_estimates import _make_config, _write_files

FILES = ["a.py", "b.py", "c.py"]
DIMS = ["security", "performance"]


def _config(tmp_path: Path, **kw):
    src = tmp_path / "src"
    _write_files(src, FILES)
    return _make_config(src, FILES, **kw)


def _warm(config, dim: str, files: list[str]) -> None:
    cache = LocalFileBackend()
    for f in files:
        key = build_cache_key_for_file(config, f, dim)
        cache.put(key, CacheEntry(
            key=key, schema_version=1, findings=[], files_read=1,
            file_path=f, dimension=dim, model_id="test-model",
        ))


def _count_hashes(monkeypatch) -> list[Path]:
    calls: list[Path] = []

    def counting(path: Path):
        calls.append(path)
        return hash_file(path)

    monkeypatch.setattr("quodeq.analysis.cache._key_provenance.hash_file", counting)
    return calls


def test_count_only_estimates_match_full_classify(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _warm(config, "security", ["a.py"])

    assert compute_dim_estimates(config, DIMS, count_only=True) == compute_dim_estimates(config, DIMS)


def test_count_only_never_prioritizes(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)

    def boom(*_a, **_kw):
        raise AssertionError("prioritize_files called on the estimates path")

    monkeypatch.setattr(source_files, "prioritize_files", boom)
    result = compute_dim_estimates(config, DIMS, count_only=True)

    assert result["security"]["total"] == len(FILES)


def test_pipeline_estimates_still_prioritize(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    seen: list[str] = []
    real = source_files.prioritize_files

    def spy(files, src, dim_id, **kw):
        seen.append(dim_id)
        return real(files, src, dim_id, **kw)

    monkeypatch.setattr(source_files, "prioritize_files", spy)
    compute_dim_estimates(config, DIMS)

    assert seen == DIMS


def test_hash_memo_hashes_each_file_once(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    config.content_hash_memo = {}
    calls = _count_hashes(monkeypatch)

    compute_dim_estimates(config, DIMS, count_only=True)

    assert sorted(p.name for p in calls) == FILES


def test_without_memo_each_dimension_hashes(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    calls = _count_hashes(monkeypatch)

    compute_dim_estimates(config, DIMS, count_only=True)

    assert len(calls) == len(FILES) * len(DIMS)


def test_memo_does_not_change_counts(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _warm(config, "security", ["a.py", "b.py"])
    plain = compute_dim_estimates(config, DIMS, count_only=True)

    config.content_hash_memo = {}
    assert compute_dim_estimates(config, DIMS, count_only=True) == plain


def test_endpoint_payload_uses_the_fast_path(tmp_path: Path, monkeypatch) -> None:
    from quodeq.analysis import estimates

    captured: dict = {}

    def fake_compute(config, dimensions, **kw):
        captured["count_only"] = kw.get("count_only", False)
        captured["memo"] = config.content_hash_memo
        return {d: {"count": 0, "reason": "empty", "total": 0, "cached": 0, "excluded": 0} for d in dimensions}

    monkeypatch.setattr(estimates, "compute_dim_estimates", fake_compute)
    monkeypatch.setattr(estimates, "_resolve_repo_source", lambda _pd: (tmp_path, None))
    monkeypatch.setattr(estimates, "_build_estimate_config", lambda *a: _config(tmp_path))
    monkeypatch.setattr(estimates, "load_analysis_context", lambda config: (DIMS, None))

    estimates.project_estimates_payload(tmp_path, None, False)

    assert captured["count_only"] is True
    assert captured["memo"] == {}


def test_count_only_reads_no_cache_entry(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    _warm(config, "security", FILES)

    def boom(self, key):
        raise AssertionError("count_only read a cache entry body")

    monkeypatch.setattr(LocalFileBackend, "get", boom)
    result = compute_dim_estimates(config, ["security"], count_only=True)

    assert (result["security"]["count"], result["security"]["cached"]) == (0, len(FILES))
