"""Per-project JSON artifacts: ``repository_info.json`` and ``scan.json``.

Services used to read/modify/write these files directly (json.loads +
read_text/write_text inline), scattering the on-disk format across the
service layer. The mechanics live here; services keep the decision logic
and delegate the I/O. Reads are best-effort (None on absent/corrupt/
non-dict payloads — the recurring non-dict-JSON crash class), writes are
best-effort too (False on failure) so callers keep their long-standing
swallow semantics explicitly.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from quodeq.core.types.scan import ScanData

REPOSITORY_INFO_FILENAME = "repository_info.json"
SCAN_FILENAME = "scan.json"


def repository_info_exists(project_dir: Path) -> bool:
    """True when ``repository_info.json`` exists.

    Pure presence probe — an unreadable record still marks the directory
    as a registered project, so callers that only need "is this a
    project?" must not fold it into :func:`read_repository_info`'s
    None-on-corrupt contract.
    """
    return (project_dir / REPOSITORY_INFO_FILENAME).exists()


def read_repository_info(project_dir: Path) -> dict | None:
    """Parsed ``repository_info.json``, or None when absent, corrupt, or
    not a JSON object."""
    path = project_dir / REPOSITORY_INFO_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_repository_info(project_dir: Path, data: dict) -> bool:
    """Write ``repository_info.json``; False when the write fails."""
    payload = json.dumps(data, indent=2)
    try:
        (project_dir / REPOSITORY_INFO_FILENAME).write_text(payload, encoding="utf-8")
    except OSError:
        return False
    return True


def read_scan_total_files(project_dir: Path) -> int:
    """``total_files`` from ``scan.json``; 0 when absent, corrupt, or non-int."""
    try:
        data = json.loads((project_dir / SCAN_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    raw = data.get("total_files") if isinstance(data, dict) else None
    return int(raw) if isinstance(raw, int) else 0


def write_scan_json(scan: ScanData, output_dir: Path) -> None:
    """Persist scan data as ``scan.json``, creating *output_dir* if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dataclasses.asdict(scan), indent=2)
    (output_dir / SCAN_FILENAME).write_text(payload, encoding="utf-8")
