"""Load stored dimension reports into compact rows for the grade calibration harness.

Reads ``<root>/<project>/<run>/evaluation/<dimension>.json`` plus the run's
``status.json`` (model) and the root's ``project_index.json`` (project names).
Each finding is reduced to its rule, severity and file: no snippet and no
message survives loading, so nothing downstream can print one.

The project size is ``sourceFileCount`` alone, as in production: a report
without one keeps ``files=0``, which the spread reads as an unknown size.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from quodeq.core.scoring.mass import finding_key  # noqa: E402
from quodeq.core.scoring.constants import Grade  # noqa: E402

ENCODING = "utf-8"
INDEX_FILE = "project_index.json"
STATUS_FILE = "status.json"
EVALUATION_GLOB = "*/*/evaluation/*.json"
INDEX_KEY_SEPARATOR = "\x00"
DEFAULT_SEVERITY = "minor"


@dataclass(frozen=True, slots=True)
class Report:
    """One stored dimension report, reduced to what the formula needs."""

    project: str
    dimension: str
    date: str
    model: str
    run: str
    files: int
    cur: float
    principles: dict[str, tuple[list[dict], list[dict]]]


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding=ENCODING))
    except (OSError, ValueError):
        return None


def _project_names(root: Path) -> dict[str, str]:
    index = _read_json(root / INDEX_FILE)
    if not isinstance(index, dict):
        return {}
    return {str(v): str(k).split(INDEX_KEY_SEPARATOR)[0] for k, v in index.items()}


def _model(run_dir: Path) -> str:
    status = _read_json(run_dir / STATUS_FILE)
    if not isinstance(status, dict):
        return ""
    return f"{status.get('ai_provider')}/{status.get('ai_model')}"


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


def _stored_score(data: dict) -> float | None:
    try:
        return float(str(data.get("overallScore")).split("/")[0])
    except ValueError:
        return None


def _reduce(item: dict) -> dict:
    return {"req": finding_key(item), "severity": item.get("severity") or DEFAULT_SEVERITY, "file": str(item.get("file") or "")}


def _principles(data: dict) -> dict[str, tuple[list[dict], list[dict]]]:
    """``{principle: (violations, compliance)}`` for the principles that were graded and have findings."""
    graded = {
        str(p.get("name")): ([], [])
        for p in data.get("principles") or []
        if isinstance(p, dict) and p.get("grade") != Grade.INSUFFICIENT
    }
    for slot, key in ((0, "violations"), (1, "compliance")):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("principle") in graded:
                graded[item["principle"]][slot].append(_reduce(item))
    return {name: pair for name, pair in graded.items() if pair[0] or pair[1]}


def _project_name(data: dict, names: dict[str, str], project_dir: str) -> str:
    named = names.get(project_dir)
    if named:
        return named
    return Path(str(data.get("project") or "").rstrip("/")).name or project_dir


def _load_one(path: Path, names: dict[str, str]) -> Report | None:
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    cur = _stored_score(data)
    principles = _principles(data)
    if cur is None or not principles:
        return None
    run_dir = path.parents[1]
    return Report(
        project=_project_name(data, names, run_dir.parent.name),
        dimension=str(data.get("dimension") or path.stem),
        date=str(data.get("date") or "")[:10],
        model=_model(run_dir),
        run=run_dir.name,
        files=_as_int(data.get("sourceFileCount")),
        cur=cur,
        principles=principles,
    )


def load_reports(roots: list[Path]) -> list[Report]:
    """Every readable dimension report under *roots*, in a stable order."""
    reports: list[Report] = []
    for root in roots:
        names = _project_names(root)
        for path in sorted(root.glob(EVALUATION_GLOB)):
            report = _load_one(path, names)
            if report is not None:
                reports.append(report)
    return reports
