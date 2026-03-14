"""Run discovery, date parsing, and report aggregation for filesystem reports.

NOTE: Storage is filesystem-based. To support alternative backends (S3, database),
introduce a RunStorage port/protocol and adapt callers.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from quodeq.adapters.fs.report_parser.json_parser import parse_evidence_file, parse_report_json
from quodeq.shared.logging import log_debug
from quodeq.shared.utils import is_repo_url
from quodeq.shared.validation import validate_path_segment


@dataclass(frozen=True)
class RunInfo:
    """Metadata for a single evaluation run (ID and date information)."""

    run_id: str
    date_iso: str | None
    date_label: str


def safe_read_dir(path: Path) -> list[os.DirEntry[str]]:
    """List directory entries, returning an empty list on OS errors."""
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError as exc:
        logging.getLogger(__name__).debug("Could not list directory %s: %s", path.name, exc)
        return []


def _normalize_date(raw: str) -> tuple[str, str] | None:
    """Parse a date/datetime string and return (sortable_iso, human_label).

    Accepts ISO datetime (2026-03-01T14:30:25), ISO date (2026-03-01),
    or compact date (20260301).  The first element is the full string
    (including time when available) so that same-day runs sort correctly.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            sortable = parsed.isoformat(timespec='seconds') if "T" in fmt else parsed.date().isoformat()
            label = f"{parsed.year}-{parsed.month:02d}-{parsed.day:02d}"
            return sortable, label
        except ValueError:
            continue
    return None


def _find_date_in_dir(directory: Path, suffix: str) -> tuple[str | None, str] | None:
    """Scan JSON files in *directory* matching *suffix* for a parsable date field."""
    for entry in safe_read_dir(directory):
        if not entry.is_file() or not entry.name.endswith(suffix):
            continue
        try:
            data = json.loads(Path(entry.path).read_text())
            raw = data.get("date")
            if raw:
                result = _normalize_date(str(raw))
                if result:
                    return result
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            log_debug(f"Failed to read date from {entry.name}: {exc}")
    return None


def _parse_run_date(reports_root: Path, project: str, run_id: str) -> tuple[str | None, str]:
    """Read the date from evidence or evaluation files in a run directory."""
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id

    result = _find_date_in_dir(run_dir / "evidence", "_evidence.json")
    if result:
        return result

    result = _find_date_in_dir(run_dir / "evaluation", ".json")
    if result:
        return result

    fallback = _normalize_date(run_id)
    if fallback:
        return fallback
    return None, run_id


def build_repository_info(repo: str, discipline: str | None) -> dict[str, str | None]:
    """Build a repository metadata dict from a local path or remote URL."""
    if is_repo_url(repo):
        name = repo.split("/")[-1].replace(".git", "")
        return {
            "name": name,
            "discipline": discipline,
            "location": "online",
            "path": repo,
        }
    resolved = Path(repo).resolve()
    return {
        "name": resolved.name,
        "discipline": discipline,
        "location": "local",
        "path": resolved.name,
    }


def _load_markdown_backed_evals(
    entries: list[os.DirEntry[str]], evaluation_dir: Path,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Load evaluations for dimensions that have a companion _eval.md file."""
    evaluations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry.is_file() or not entry.name.endswith("_eval.md"):
            continue
        dimension = entry.name.removesuffix("_eval.md")
        json_path = evaluation_dir / f"{dimension}.json"
        parsed = parse_report_json(json_path) if json_path.exists() else None
        if parsed:
            evaluations.append(parsed)
            seen.add(dimension)
    return evaluations, seen


def _load_json_only_evals(
    entries: list[os.DirEntry[str]], seen: set[str],
) -> list[dict[str, Any]]:
    """Load evaluations from JSON files not already covered by markdown-backed pass."""
    evaluations: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        dimension = entry.name.removesuffix(".json")
        if dimension in seen:
            continue
        parsed = parse_report_json(Path(entry.path))
        if parsed:
            evaluations.append(parsed)
    return evaluations


def _load_evaluations(evaluation_dir: Path) -> list[dict[str, Any]]:
    """Load parsed evaluation dicts from a run's evaluation directory."""
    entries = safe_read_dir(evaluation_dir)
    evaluations, seen = _load_markdown_backed_evals(entries, evaluation_dir)
    evaluations.extend(_load_json_only_evals(entries, seen))
    return evaluations


def _load_evidence_map(evidence_dir: Path) -> dict[str, dict[str, Any]]:
    """Load evidence files keyed by dimension name."""
    evidence_map: dict[str, dict[str, Any]] = {}
    for entry in safe_read_dir(evidence_dir):
        if entry.is_file() and entry.name.endswith("_evidence.json"):
            parsed_ev = parse_evidence_file(Path(entry.path))
            evidence_map[parsed_ev["dimension"]] = parsed_ev
    return evidence_map


def read_run_data(reports_root: Path, project: str, run_id: str) -> list[dict[str, Any]]:
    """Load all dimension evaluations and evidence for a single run."""
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id
    evaluations = _load_evaluations(run_dir / "evaluation")
    evidence_map = _load_evidence_map(run_dir / "evidence")

    dimensions = []
    for evaluation in evaluations:
        dimension = evaluation.get("dimension")
        evidence = evidence_map.get(dimension, {})
        dimensions.append(
            {
                **evaluation,
                "sourceFileCount": evidence.get("sourceFileCount"),
                "evidenceDate": evidence.get("date"),
                "discipline": evidence.get("discipline"),
            }
        )

    dimensions.sort(key=lambda item: item.get("dimension") or "")
    return dimensions


def list_runs(reports_root: Path, project: str) -> list[RunInfo]:
    """Return all runs for a project, sorted newest-first by date."""
    validate_path_segment(project)
    project_dir = reports_root / project
    run_infos: list[RunInfo] = []
    for entry in safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        date_iso, date_label = _parse_run_date(reports_root, project, entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    return run_infos


@dataclass(frozen=True)
class RunLookupCache:
    """Pre-computed data to avoid repeated I/O when looking up previous runs."""

    runs: list[RunInfo]
    get_run_data: Callable[[str], list[dict[str, Any]]]


def _get_previous_run_for_dimension(
    reports_root: Path,
    project: str,
    current_run_id: str,
    dimension: str,
    *,
    cache: RunLookupCache | None = None,
) -> dict[str, Any] | None:
    """Return the most recent run data for *dimension* before *current_run_id*, or None.

    Callers processing multiple dimensions for the same project should pass
    a *cache* (built from a single ``list_runs`` call and a dict-backed
    callable) to share I/O across calls rather than repeating the directory
    scan and file reads for each dimension.
    """
    validate_path_segment(project, current_run_id)
    project_path = reports_root / project
    if not project_path.exists():
        return None
    all_runs = cache.runs if cache is not None else list_runs(reports_root, project)
    current_idx = next((i for i, r in enumerate(all_runs) if r.run_id == current_run_id), -1)
    if current_idx < 0:
        return None
    _data_cache: dict[str, list[dict[str, Any]]] = {}

    def _fetch(run_id: str) -> list[dict[str, Any]]:
        if cache is not None:
            return cache.get_run_data(run_id)
        if run_id not in _data_cache:
            _data_cache[run_id] = read_run_data(reports_root, project, run_id)
        return _data_cache[run_id]

    for run_info in all_runs[current_idx + 1:]:
        dims = _fetch(run_info.run_id)
        dims_by_name = {d.get("dimension"): d for d in dims if d.get("dimension")}
        dim = dims_by_name.get(dimension)
        if dim:
            return {"runId": run_info.run_id, "dimension": dim}
    return None
