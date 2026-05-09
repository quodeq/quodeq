"""Discard path wipes V2 cache entries + JSONL for incomplete dims."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from quodeq.analysis.cache import LocalFileBackend, CacheEntry
from quodeq.shared.dimensions_state import DimState, write_dim_state


def _seed_cache_entries(cache_root: Path, keys: list[str]) -> LocalFileBackend:
    cache = LocalFileBackend(root=cache_root)
    for k in keys:
        cache.put(k, CacheEntry(
            key=k, schema_version=2, findings=[],
            files_read=1, file_path=f"{k}.py", dimension="d", model_id="m",
        ))
    return cache


def _seed_run(tmp_path: Path) -> tuple[Path, Path]:
    reports = tmp_path / "reports"
    run = reports / "proj" / "run-1"
    (run / "evidence").mkdir(parents=True)
    (run / "evaluation").mkdir(parents=True)
    return reports, run


class TestDiscardWipesV2Cache:
    def test_incomplete_dim_keys_deleted_done_dim_untouched(
        self, tmp_path: Path, monkeypatch,
    ):
        from quodeq.services.evaluation_mixin import _discard_partial_dim_state

        reports, run = _seed_run(tmp_path)

        # Two dims:
        # - d_inc: incomplete, has 2 cache entries via sidecar
        # - d_done: cleanly scored
        (run / "evidence" / "d_inc_dispatch_keys.json").write_text(
            json.dumps({"a.py": "kkkkk1", "b.py": "kkkkk2"}),
        )
        (run / "evidence" / "d_inc_evidence.jsonl").write_text('{"file":"a.py"}\n')
        (run / "evidence" / "d_inc_queue.json").write_text("{}")
        (run / "evidence" / "d_done_dispatch_keys.json").write_text(
            json.dumps({"c.py": "kkkkk3"}),
        )
        (run / "evaluation" / "d_done.json").write_text("{}")

        write_dim_state(run, "d_inc", DimState.PENDING)
        write_dim_state(run, "d_inc", DimState.RUNNING)
        write_dim_state(run, "d_inc", DimState.INCOMPLETE, reason="cancelled_by_user")
        write_dim_state(run, "d_done", DimState.PENDING)
        write_dim_state(run, "d_done", DimState.RUNNING)
        write_dim_state(run, "d_done", DimState.DONE)

        cache_root = tmp_path / "cache"
        cache = _seed_cache_entries(cache_root, ["kkkkk1", "kkkkk2", "kkkkk3"])
        monkeypatch.setattr(
            "quodeq.services.evaluation_mixin._open_cache",
            lambda: cache,
        )

        _discard_partial_dim_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        assert cache.get("kkkkk1") is None
        assert cache.get("kkkkk2") is None
        assert cache.get("kkkkk3") is not None  # done dim untouched
        assert not (run / "evidence" / "d_inc_evidence.jsonl").exists()

    def test_missing_sidecar_continues_and_wipes_jsonl(
        self, tmp_path: Path,
    ):
        """A crash before the sidecar is written must not block discard."""
        from quodeq.services.evaluation_mixin import _discard_partial_dim_state

        reports, run = _seed_run(tmp_path)
        # Dim is incomplete but no sidecar (e.g., crashed before writing it).
        (run / "evidence" / "d_inc_evidence.jsonl").write_text('{"file":"a.py"}\n')
        write_dim_state(run, "d_inc", DimState.PENDING)
        write_dim_state(run, "d_inc", DimState.RUNNING)
        write_dim_state(run, "d_inc", DimState.INCOMPLETE, reason="failed_exception")

        # Should not raise even with no sidecar.
        _discard_partial_dim_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        # JSONL still gets wiped despite the missing sidecar.
        assert not (run / "evidence" / "d_inc_evidence.jsonl").exists()

    def test_no_dim_states_file_falls_back_to_legacy_behavior(
        self, tmp_path: Path,
    ):
        """Pre-Slice-2 runs (no dimensions.json) still work: only the
        queue + fingerprint wipe runs, V2 cache is untouched."""
        from quodeq.services.evaluation_mixin import _discard_partial_dim_state

        reports, run = _seed_run(tmp_path)
        (run / "evidence" / "d1_queue.json").write_text("{}")
        (run / "evidence" / "d1_fingerprint.json").write_text("{}")

        # No dimensions.json. Discard should not crash.
        _discard_partial_dim_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        assert not (run / "evidence" / "d1_queue.json").exists()
        assert not (run / "evidence" / "d1_fingerprint.json").exists()
