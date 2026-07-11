"""Parser for detailed JSON evaluation files with principle breakdowns."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.core.types._serialization import to_camel_dict
from quodeq.core.evidence._req_mapping import principle_names_for_dimension
from quodeq.shared.utils import read_json
from quodeq.data.fs.report_parser._report_parsing import build_finding, empty_severity_buckets
from quodeq.data.fs.report_parser._principle_map import build_principle_map

_logger = logging.getLogger(__name__)
_OVERALL_PRINCIPLE = "Overall"


def parse_eval_from_json(
    json_path: Path, project: str, run_id: str, dimension: str,
    *, compiled_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Parse a JSON evaluation file into a detailed report with principle breakdowns.

    When *compiled_dir* is supplied, principles absent from the dimension's
    standard are dropped from the result, so a stale per-dimension JSON that
    carries a phantom principle (e.g. an unmapped "N/A" group) no longer renders
    as an extra dashboard card or radial vertex. Because the dashboard re-parses
    the frozen JSON on every read, this also corrects already-written runs
    without rewriting them.
    """
    try:
        data = read_json(json_path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to parse evaluation %s: %s", json_path.name, exc)
        return None

    canonical = principle_names_for_dimension(dimension, compiled_dir=compiled_dir)

    def _in_standard(name: Any) -> bool:
        # Permissive when no standard is available (canonical empty).
        return not canonical or name in canonical

    principle_grades = [
        {
            "principle": p.get("name"),
            "score": p.get("score"),
            "grade": p.get("grade"),
            "isOverall": False,
        }
        for p in data.get("principles", [])
        if _in_standard(p.get("name"))
    ]
    principle_grades.append(
        {
            "principle": _OVERALL_PRINCIPLE,
            "score": data.get("overallScore"),
            "grade": data.get("overallGrade"),
            "isOverall": True,
        }
    )

    principle_map = build_principle_map(data)
    if canonical:
        principle_map = {k: v for k, v in principle_map.items() if k in canonical}

    # Intentional full materialization: these lists are included in a dict that
    # gets JSON-serialized by the caller, so lazy iteration would not help.
    violations = [to_camel_dict(build_finding(v, include_severity=True)) for v in data.get("violations", [])]
    compliance = [to_camel_dict(build_finding(c, include_severity=False)) for c in data.get("compliance", [])]

    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "principleGrades": principle_grades,
        "principles": list(principle_map.values()),
        "violations": violations,
        "compliance": compliance,
        "priorityRemediation": empty_severity_buckets(),
        "rawContent": None,
    }
