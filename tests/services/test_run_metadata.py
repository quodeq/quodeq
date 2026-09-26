"""``read_run_metadata`` joins status.json, the reports and dim_estimates.json."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.run_metadata import read_run_metadata

_SHA = "0123456789abcdef0123456789abcdef01234567"
_SOURCE_COUNT = 150
_FILES_READ = 120
_COVERAGE = 80.0
_MISSES = 30
_CACHED = 90
_EXCLUDED = 30


def _seed(run_dir: Path) -> None:
    (run_dir / "status.json").write_text(json.dumps({
        "state": "done", "started_at": "2026-09-26T00:00:00Z", "commit_sha": _SHA}), encoding="utf-8")
    (run_dir / "evaluation").mkdir()
    (run_dir / "evaluation" / "security.json").write_text(json.dumps({
        "dimension": "security", "sourceFileCount": _SOURCE_COUNT, "filesRead": _FILES_READ,
        "coveragePct": _COVERAGE, "principles": [], "violations": [], "compliance": []}),
        encoding="utf-8")
    (run_dir / "dim_estimates.json").write_text(json.dumps({
        "security": {"count": _MISSES, "total": _SOURCE_COUNT, "cached": _CACHED,
                     "excluded": _EXCLUDED}}), encoding="utf-8")


def test_read_run_metadata_joins_sources(tmp_path: Path) -> None:
    _seed(tmp_path)
    meta = read_run_metadata(tmp_path)
    assert meta["commitSha"] == _SHA
    assert meta["coverage"]["security"] == {
        "sourceFileCount": _SOURCE_COUNT, "filesRead": _FILES_READ, "coveragePct": _COVERAGE,
        "cached": _CACHED, "misses": _MISSES, "excluded": _EXCLUDED,
    }


def test_read_run_metadata_tolerates_missing_files(tmp_path: Path) -> None:
    assert read_run_metadata(tmp_path) == {"commitSha": None, "coverage": {}}
