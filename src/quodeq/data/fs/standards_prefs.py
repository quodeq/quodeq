"""Filesystem store for per-project standards preferences.

Reads/writes ``<project root>/.quodeq/standards-visibility.json`` and reads
``standards-overrides.json`` + compiled dimension files. The pure logic
(validation, partitioning, param resolution) stays in ``core/standards/``;
the API layer goes through ``services/standards_prefs.py``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.standards.overrides import OVERRIDES_RELPATH
from quodeq.core.standards.visibility import (
    DEFAULT_VISIBLE_STANDARDS,
    VISIBILITY_RELPATH,
    normalize_ids,
)

_logger = logging.getLogger(__name__)


def load_visible_standard_ids(project_root: str | Path | None) -> tuple[str, ...]:
    """Visible standard ids for a project; defaults when absent or malformed."""
    if not project_root:
        return DEFAULT_VISIBLE_STANDARDS
    path = Path(project_root) / VISIBILITY_RELPATH
    if not path.is_file():
        return DEFAULT_VISIBLE_STANDARDS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Ignoring malformed standards visibility %s: %s", path, exc)
        return DEFAULT_VISIBLE_STANDARDS
    ids = data.get("visibleStandardIds") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        _logger.warning(
            "Ignoring standards visibility %s: no 'visibleStandardIds' array", path)
        return DEFAULT_VISIBLE_STANDARDS
    # An explicitly empty list is a real selection ("hide everything") and is
    # returned as-is; only a missing/!list value falls back to the defaults.
    return normalize_ids(ids)


def save_visible_standard_ids(project_root: str | Path, ids: list[str]) -> None:
    """Write the selection, creating ``.quodeq/`` when needed."""
    path = Path(project_root) / VISIBILITY_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "visibleStandardIds": list(normalize_ids(ids))}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_project_overrides(project_root: str | Path | None) -> dict[str, dict]:
    """Load ``{req_id: {param: value}}``; ``{}`` when absent or malformed."""
    if not project_root:
        return {}
    path = Path(project_root) / OVERRIDES_RELPATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Ignoring malformed standards overrides %s: %s", path, exc)
        return {}
    overrides = data.get("overrides") if isinstance(data, dict) else None
    if not isinstance(overrides, dict):
        _logger.warning("Ignoring standards overrides %s: no 'overrides' object", path)
        return {}
    return {req_id: vals for req_id, vals in overrides.items() if isinstance(vals, dict)}


def save_project_overrides(project_root: str | Path, overrides: dict[str, dict]) -> None:
    """Write ``{req_id: {param: value}}``, creating ``.quodeq/`` when needed."""
    path = Path(project_root) / OVERRIDES_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": 1, "overrides": overrides}, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")


def clear_project_overrides(project_root: str | Path) -> None:
    """Remove the overrides file. No-op when it does not exist."""
    (Path(project_root) / OVERRIDES_RELPATH).unlink(missing_ok=True)


def collect_declared_params(compiled_dir: Path) -> dict[str, dict]:
    """Collect ``{req_id: params_spec}`` across every compiled dimension file."""
    declared: dict[str, dict] = {}
    for path in sorted(Path(compiled_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for principle in data.get("principles", []):
            for req in principle.get("requirements", []):
                if req.get("id") and req.get("params"):
                    declared[req["id"]] = req["params"]
    return declared
