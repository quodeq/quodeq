"""I/O adapters -- persist pre-built report dicts to disk."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.types import ScoringResult
from quodeq.core.evidence.model import Evidence
from quodeq.shared.validation import validate_path_segment

from quodeq.analysis._report_assembly import build_full_report, build_dashboard_report


def _persist_json(data: dict, path: Path) -> None:
    """Write a report dict as formatted JSON to *path* (I/O adapter)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(data, indent=2))
    except OSError as exc:
        raise OSError(f"Failed to write report to {path}: {exc}") from exc


def write_reports(
    evidence: Evidence, scores: ScoringResult | dict, output_dir: Path,
) -> None:
    """Build and persist full + dashboard report files (I/O adapter)."""
    full_report = build_full_report(evidence, scores)
    dashboard_report = build_dashboard_report(evidence, scores)

    dim = evidence.language
    validate_path_segment(dim)
    _persist_json(full_report, output_dir / f"{dim}_full.json")
    _persist_json(dashboard_report, output_dir / f"{dim}.json")


def write_dimension_report(
    evidence: Evidence, scores: ScoringResult | dict, dimension: str, output_dir: Path,
) -> None:
    """Build and persist a per-dimension report file (I/O adapter)."""
    validate_path_segment(dimension)

    report = build_dashboard_report(evidence, scores)
    report["dimension"] = dimension
    _persist_json(report, output_dir / f"{dimension}.json")
