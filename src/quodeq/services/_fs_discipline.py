"""Language-stat and discipline-inference helpers for the filesystem action
provider.

Split out of _fs_metadata.py (Task 13). ``_has_fingerprints`` logs via the
``_fs_metadata`` facade's logger (looked up at call time, deferred to avoid
a circular import) rather than creating its own ``logging.getLogger`` here --
tests assert the warning under the "quodeq.services._fs_metadata" logger
name, and the logging-boundary ratchet (tests/tools/test_logging_boundary.py)
already declares _fs_metadata.py as a site; a new site in this sibling would
need its own declaration.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services._wiring import safe_read_dir


def _read_language_stats(reports_root: Path, entry_name: str, runs: list[RunInfo]) -> dict[str, int]:
    """Read language_stats from the latest run's manifest.json."""
    for run in runs:
        manifest_path = reports_root / entry_name / run.run_id / "evidence" / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            stats = data.get("language_stats") or {}
            if stats:
                return {k.lstrip("."): v for k, v in stats.items()}
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _read_discipline_from_eval(eval_path: Path) -> str | None:
    """Try to read a discipline string from a single evidence JSON file."""
    try:
        return json.loads(eval_path.read_text(encoding="utf-8")).get("discipline") or None
    except (OSError, json.JSONDecodeError):
        return None


def _find_discipline_in_run(evidence_dir: Path) -> str | None:
    """Search a single run's evidence directory for a discipline string."""
    for ev in safe_read_dir(evidence_dir):
        if ev.name.endswith("_evidence.json"):
            found = _read_discipline_from_eval(Path(ev.path))
            if found:
                return found
    return None


def _infer_discipline(reports_root: Path, project: str) -> str | None:
    """Infer discipline from the most recent evidence file."""
    for run in sorted(safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
        if not run.is_dir():
            continue
        found = _find_discipline_in_run(reports_root / project / run.name / "evidence")
        if found:
            return found
    return None


def _has_fingerprints(reports_root: Path, project: str) -> bool:
    """Check if any evaluation run has fingerprint files for this project."""
    project_dir = reports_root / project
    if not project_dir.exists():
        return False
    try:
        for run_dir in sorted(project_dir.iterdir(), reverse=True):
            evidence_dir = run_dir / "evidence"
            if not evidence_dir.is_dir():
                continue
            if any(f.name.endswith("_fingerprint.json") for f in evidence_dir.iterdir()):
                return True
    except OSError as e:
        from quodeq.services._fs_metadata import _logger

        _logger.warning("Could not read fingerprint dir %s: %s", project_dir, e)
    return False
