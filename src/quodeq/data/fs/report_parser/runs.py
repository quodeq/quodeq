"""Run discovery, date parsing, and report aggregation for filesystem reports.

The ``RunStorage`` protocol defines the interface callers depend on.
The module-level functions (``read_run_data``, ``list_runs``) provide the
default filesystem implementation.  Alternative backends (S3, database)
should implement ``RunStorage`` and be injected at the call site.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from quodeq.core.types import DimensionResult
from quodeq.core.types.mappers import parse_dimension_result
from quodeq.data.fs.report_parser._date_utils import find_date_in_dir, normalize_date
from quodeq.data.fs.report_parser._run_lookup import (
    RunLookupCache as RunLookupCache,
    _get_previous_run_for_dimension as _get_previous_run_for_dimension,
    _make_caching_fetcher as _make_caching_fetcher,
)
from quodeq.data.fs.report_parser.json_parser import parse_evidence_file, parse_report_json
from quodeq.shared.utils import is_repo_url
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)

_GIT_SUFFIX = ".git"


@dataclass(frozen=True)
class RunInfo:
    """Metadata for a single evaluation run (ID and date information)."""

    run_id: str
    date_iso: str | None
    date_label: str


@runtime_checkable
class RunStorage(Protocol):
    """Interface for run data storage backends.

    The default filesystem implementation is provided by the module-level
    ``read_run_data`` and ``list_runs`` functions.  Alternative backends
    (S3, database) should implement this protocol.
    """

    def read_run_data(self, project: str, run_id: str) -> list[DimensionResult]:
        """Load all dimension evaluations and evidence for a single run."""
        ...

    def list_runs(self, project: str, *, limit: int = 0) -> list[RunInfo]:
        """Return runs for a project, sorted newest-first by date."""
        ...


def safe_read_dir(path: Path) -> list[os.DirEntry[str]]:
    """List directory entries, returning an empty list on OS errors.

    Example::

        entries = safe_read_dir(Path("/data/reports"))
    """
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError as exc:
        _logger.debug(
            "Could not list directory %s: %s. Check path exists and file permissions are correct",
            path.name,
            exc,
        )
        return []


def _parse_run_date(reports_root: Path, project: str, run_id: str) -> tuple[str | None, str]:
    """Read the date from evidence or evaluation files in a run directory."""
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id

    result = find_date_in_dir(run_dir / "evidence", "_evidence.json", safe_read_dir)
    if result:
        return result

    result = find_date_in_dir(run_dir / "evaluation", ".json", safe_read_dir)
    if result:
        return result

    fallback = normalize_date(run_id)
    if fallback:
        return fallback
    return None, run_id


def build_repository_info(repo: str, discipline: str | None) -> dict[str, str | None]:
    """Build a repository metadata dict from a local path or remote URL.

    Example::

        build_repository_info("https://github.com/org/repo.git", "python")
    """
    if is_repo_url(repo):
        name = repo.split("/")[-1].replace(_GIT_SUFFIX, "")
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
    """Load parsed evaluation dicts from a run's evaluation directory.

    Supports both flat layouts (single-target) and nested layouts (multi-target)
    where each subdirectory is a target module.
    """
    entries = safe_read_dir(evaluation_dir)
    evaluations, seen = _load_markdown_backed_evals(entries, evaluation_dir)
    evaluations.extend(_load_json_only_evals(entries, seen))

    # Scan target subdirectories for multi-target runs
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        target_dir = evaluation_dir / entry.name
        sub_entries = safe_read_dir(target_dir)
        sub_evals, sub_seen = _load_markdown_backed_evals(sub_entries, target_dir)
        for ev in sub_evals:
            ev.setdefault("module", entry.name)
        evaluations.extend(sub_evals)
        json_evals = _load_json_only_evals(sub_entries, sub_seen)
        for ev in json_evals:
            ev.setdefault("module", entry.name)
        evaluations.extend(json_evals)

    return evaluations


def _load_evidence_from_dir(directory: Path, module: str = "") -> dict[str, dict[str, Any]]:
    """Load evidence files from a single directory, keyed by dimension name."""
    evidence_map: dict[str, dict[str, Any]] = {}
    for entry in safe_read_dir(directory):
        if entry.is_file() and entry.name.endswith("_evidence.json"):
            parsed_ev = parse_evidence_file(Path(entry.path))
            dimension = parsed_ev.get("dimension")
            if dimension is None:
                _logger.warning(
                    "Evidence file %s missing 'dimension' key, skipping", entry.name,
                )
                continue
            if module:
                parsed_ev["module"] = module
            evidence_map[dimension] = parsed_ev
    return evidence_map


def _load_evidence_map(evidence_dir: Path) -> dict[str, dict[str, Any]]:
    """Load evidence files keyed by dimension name.

    Supports both flat (single-target) and nested (multi-target) layouts.
    """
    evidence_map = _load_evidence_from_dir(evidence_dir)

    # Scan target subdirectories
    for entry in safe_read_dir(evidence_dir):
        if entry.is_dir() and not entry.name.startswith("."):
            sub_map = _load_evidence_from_dir(evidence_dir / entry.name, module=entry.name)
            evidence_map.update(sub_map)

    return evidence_map


def read_run_data(reports_root: Path, project: str, run_id: str) -> list[DimensionResult]:
    """Load all dimension evaluations and evidence for a single run.

    Example::

        dims = read_run_data(Path("/reports"), "my-project", "20260301")
    """
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id
    evaluations = _load_evaluations(run_dir / "evaluation")
    evidence_map = _load_evidence_map(run_dir / "evidence")

    dimensions: list[DimensionResult] = []
    for evaluation in evaluations:
        dimension = evaluation.get("dimension")
        evidence = evidence_map.get(dimension, {})
        merged = {
            **evaluation,
            "sourceFileCount": evidence.get("sourceFileCount"),
            "evidenceDate": evidence.get("date"),
            "discipline": evidence.get("discipline"),
        }
        dimensions.append(parse_dimension_result(merged))

    dimensions.sort(key=lambda item: item.dimension)
    return dimensions


def list_runs(reports_root: Path, project: str, *, limit: int = 0) -> list[RunInfo]:
    """Return runs for a project, sorted newest-first by date.

    When *limit* > 0 only the most recent *limit* runs are returned.

    Example::

        runs = list_runs(Path("/reports"), "my-project", limit=5)
    """
    validate_path_segment(project)
    project_dir = reports_root / project
    run_infos: list[RunInfo] = []
    for entry in safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        date_iso, date_label = _parse_run_date(reports_root, project, entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    if limit > 0:
        return run_infos[:limit]
    return run_infos


