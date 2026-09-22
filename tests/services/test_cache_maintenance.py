"""The dashboard migrates and indexes the result cache off the request path."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.cache_store import migrate as mig
from quodeq.services.cache_maintenance import start_cache_maintenance


def _write_v3_entry(root: Path) -> None:
    key = "ab" * 32
    d = root / key[:2] / key[2:]
    d.mkdir(parents=True)
    (d / "entry.json").write_text(json.dumps({
        "key": key, "schema_version": 3, "findings": [], "files_read": 1,
        "file_path": "a.py", "dimension": "security", "model_id": "m",
        "file_content_hash": "aa" * 32, "language": "python",
    }))


def test_start_cache_maintenance_runs_ensure_cache_ready_in_a_daemon_thread(tmp_path: Path):
    mig._ready_memo.clear()
    root = tmp_path / "results"
    _write_v3_entry(root)
    thread = start_cache_maintenance(root, standards_dir=None)
    assert thread.daemon is True
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert mig.ready_marker(root).exists()
    assert len(list(root.rglob("entry.json"))) == 1


def test_start_cache_maintenance_survives_failures(tmp_path: Path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("nope")
    monkeypatch.setattr("quodeq.services.cache_maintenance.ensure_cache_ready", boom)
    thread = start_cache_maintenance(tmp_path / "results", standards_dir=None)
    thread.join(timeout=10)
    assert not thread.is_alive()  # swallowed and logged, never propagated
