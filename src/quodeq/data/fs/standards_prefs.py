"""Filesystem store for per-project standards preferences.

Collects declared params and requirement ids from compiled dimension files. The pure logic
(validation, partitioning, param resolution) stays in ``core/standards/``;
the API layer goes through ``services/standards_prefs.py``. The machine-local
settings store is in ``project_standards``; its public names are re-exported here.

Every read here is advisory, hand-writable config with a well-defined default,
so a parse failure of *any* kind degrades with a warning -- not just the
well-behaved ``OSError``/``ValueError``/``UnicodeDecodeError`` trio. In
particular, deeply nested JSON (tens of thousands of nested arrays, a ~160KB
file a buggy generator produces by accident) overflows the C decoder's call
stack and raises ``RecursionError``, which is a ``RuntimeError`` and would
otherwise escape and fail the scan.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.data.fs.compiled_standards import iter_compiled_standards
from quodeq.data.fs.project_standards import (  # noqa: F401 - re-exported API
    SETTINGS_VERSION,
    ProjectStandards,
    load_overrides_file,
    load_project_standards,
    project_settings_file,
    read_project_standards,
    remove_project_settings,
    save_enabled_ids,
    save_overrides,
    settings_file_for_owner,
    settings_owner_id,
    settings_reports_root,
    write_project_standards,
)

_logger = logging.getLogger(__name__)


def collect_declared_params(compiled_dir: Path) -> dict[str, dict]:
    """Collect ``{req_id: params_spec}`` across every compiled dimension file."""
    declared: dict[str, dict] = {}
    for path in sorted(Path(compiled_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            _logger.warning("Skipping unreadable declared params in %s: %s", path, exc)
            continue
        for principle in data.get("principles", []):
            for req in principle.get("requirements", []):
                if req.get("id") and req.get("params"):
                    declared[req["id"]] = req["params"]
    return declared


def collect_requirement_ids(compiled_dir: Path) -> frozenset[str]:
    """Every requirement id declared by the standards in *compiled_dir*."""
    ids: set[str] = set()
    for _stem, data in iter_compiled_standards(Path(compiled_dir)):
        for principle in data.get("principles", []):
            for req in principle.get("requirements", []) if isinstance(principle, dict) else []:
                if isinstance(req, dict) and isinstance(req.get("id"), str):
                    ids.add(req["id"])
    return frozenset(ids)
