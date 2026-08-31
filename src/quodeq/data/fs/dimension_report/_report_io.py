"""I/O adapters -- persist pre-built report dicts to disk."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from quodeq.core.types import ScoringResult
from quodeq.core.evidence.model import Evidence
from quodeq.shared.validation import validate_path_segment

from quodeq.data.fs.dimension_report._report_assembly import build_full_report, build_dashboard_report


def _persist_json(data: dict, path: Path) -> None:
    """Atomically write a report dict as formatted JSON to *path*.

    Dashboard readers poll these files and treat a parse failure as "the
    dimension does not exist", so the destination must never hold a partial
    write: serialize to a same-directory temp file and publish via rename.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=f".{path.name}.",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(path))
        tmp_path = None
    except OSError as exc:
        raise OSError(f"Failed to write report to {path}: {exc}") from exc
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
