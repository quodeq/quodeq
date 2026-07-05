"""Tests for quodeq.services._run_dimensions.configured_dimensions."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._run_dimensions import configured_dimensions


def _write(path: Path, name: str, data: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(json.dumps(data), encoding="utf-8")


def test_reads_dimensions_json_keys(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        "dimensions.json",
        {
            "schema_version": 1,
            "dimensions": {
                "security": {"state": "done"},
                "performance": {"state": "done"},
            },
        },
    )
    assert configured_dimensions(run_dir) == {"security", "performance"}


def test_prefers_dimensions_json_over_status(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        "dimensions.json",
        {"schema_version": 1, "dimensions": {"security": {"state": "done"}}},
    )
    _write(run_dir, "status.json", {"dimensions": ["security", "reliability"]})
    # dimensions.json wins when present and non-empty.
    assert configured_dimensions(run_dir) == {"security"}


def test_falls_back_to_status_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    # No dimensions.json — status.json list is the fallback signal.
    _write(run_dir, "status.json", {"dimensions": ["security", "usability"]})
    assert configured_dimensions(run_dir) == {"security", "usability"}


def test_falls_back_when_dimensions_json_empty(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(run_dir, "dimensions.json", {"schema_version": 1, "dimensions": {}})
    _write(run_dir, "status.json", {"dimensions": ["security"]})
    assert configured_dimensions(run_dir) == {"security"}


def test_empty_set_when_absent(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert configured_dimensions(run_dir) == set()


def test_empty_set_when_status_dimensions_not_a_list(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(run_dir, "status.json", {"dimensions": "security"})
    assert configured_dimensions(run_dir) == set()
