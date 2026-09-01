"""Scan-related helpers for project registration: a fresh zero-run
scan_data fallback shape, and scanning a scoped project's parent.

Split out of project_registration.py (Task 12).
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._fs_scan import scan_project


def _zero_run_scan_fallback() -> dict:
    """Fresh zero-run scan_data for a project whose scan.json is missing/corrupt.

    A factory, not a module-level constant: dict(_ZERO_RUN_SCAN_FALLBACK) used
    to only shallow-copy, so every registration that hit this fallback shared
    the same nested ``languages``/``branches``/``modules``/``file_tree``
    containers -- a caller mutating one result's list/dict silently corrupted
    every other fallback result (past and future).
    """
    return {
        "total_files": 0, "code_files": 0, "languages": {},
        "branches": [], "modules": [], "file_tree": [],
    }


def _scan_parent_project(project_dir: Path, reports_path: Path, repo_path: Path) -> None:
    """Scan the parent project directory if it lacks a scan.json."""
    info_path = project_dir / "repository_info.json"
    try:
        parent_uuid = json.loads(info_path.read_text(encoding="utf-8")).get("parent")
        if parent_uuid:
            parent_dir = reports_path / parent_uuid
            if not (parent_dir / "scan.json").exists():
                scan_project(repo_path, output_dir=parent_dir)
    except (json.JSONDecodeError, OSError):
        pass
