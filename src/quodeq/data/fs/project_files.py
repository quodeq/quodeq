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


def write_scan_json(scan: ScanData, output_dir: Path) -> None:
    """Persist scan data as ``scan.json``, creating *output_dir* if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dataclasses.asdict(scan), indent=2)
    (output_dir / SCAN_FILENAME).write_text(payload, encoding="utf-8")
