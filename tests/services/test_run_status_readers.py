from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.services._run_status_readers import _read_enriched_status_fields


def _write_status(run_dir: Path, **fields) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps(fields), encoding="utf-8")


def test_reads_status_json_once_for_all_four_fields(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_status(
        run_dir,
        dimensions=["security", "performance"],
        deadline_at="2026-09-02T20:00:00+00:00",
        ai_provider="claude",
        ai_model="sonnet",
        time_limit_s=3600,
    )

    real_read_text = Path.read_text
    read_count = {"n": 0}

    def counting_read_text(self, *a, **kw):
        if self.name == "status.json":
            read_count["n"] += 1
        return real_read_text(self, *a, **kw)

    with patch("pathlib.Path.read_text", counting_read_text):
        logs, dims, deadline, provider, model, limit = _read_enriched_status_fields(run_dir)

    assert dims == ["security", "performance"]
    assert deadline == "2026-09-02T20:00:00+00:00"
    assert provider == "claude"
    assert model == "sonnet"
    assert limit == 3600
    assert read_count["n"] == 1, f"expected 1 status.json read, got {read_count['n']}"


def test_missing_status_json_returns_all_nones(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    logs, dims, deadline, provider, model, limit = _read_enriched_status_fields(run_dir)
    assert (dims, deadline, provider, model, limit) == (None, None, None, None, None)
