"""Scan-related helpers for project registration: a fresh zero-run
scan_data fallback shape, and scanning a scoped project's parent.

Split out of project_registration.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.fs_scan import scan_project
from quodeq.services.wiring import read_repository_info, scan_json_exists


def zero_run_scan_fallback() -> dict:
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


def scan_parent_project(
    project_dir: Path, reports_path: Path, repo_path: Path, *, log: LogSink = NULL_LOG,
) -> None:
    """Scan the parent project directory if it lacks a scan.json."""
    info_path = project_dir / "repository_info.json"
    info = read_repository_info(project_dir)
    if info is None:
        log.warning(f"Could not scan parent project for {info_path}: missing or invalid repository_info.json")
        return
    parent_uuid = info.get("parent")
    if parent_uuid:
        parent_dir = reports_path / parent_uuid
        if not scan_json_exists(parent_dir):
            try:
                scan_project(repo_path, output_dir=parent_dir)
            except OSError as exc:
                log.warning(f"Could not scan parent project for {info_path}: {exc}")
