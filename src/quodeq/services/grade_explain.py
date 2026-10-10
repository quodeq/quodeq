"""``explain_dimension`` shows the arithmetic behind each principle's grade."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.scoring.explain import explain_principle
from quodeq.core.scoring.internals import finding_to_scoring_dict
from quodeq.core.scoring.params import ScoringParams, params_to_dict
from quodeq.core.scoring.mass import principle_mass, requirement_rows
from quodeq.core.types.finding import Finding
from quodeq.core.utils.io import resolve_child_dir
from quodeq.services.wiring import GradeInputs, load_grade_inputs, load_params


class DimensionNotFound(FileNotFoundError):
    """The run exists but has no findings for the requested dimension."""


def _run_dir(reports_root: Path, project: str, run_id: str) -> Path:
    project_dir = resolve_child_dir(reports_root, project)
    run_dir = resolve_child_dir(Path(project_dir), run_id) if project_dir else None
    if run_dir is None:
        raise FileNotFoundError("Run not found")
    return Path(run_dir)


def _keys_for(inputs: GradeInputs, dimension: str) -> list[tuple[str, str]]:
    """(dimension, principle) keys of *dimension*, matched case-insensitively.
    Findings with no principle have no card to explain and are skipped."""
    wanted = dimension.lower()
    keys = set(inputs.violations_by) | set(inputs.compliance_by)
    return sorted(k for k in keys if k[0].lower() == wanted and k[1])


def _explain_one(
    inputs: GradeInputs, key: tuple[str, str], params: ScoringParams,
) -> dict[str, Any]:
    findings: list[Finding] = inputs.violations_by.get(key, [])
    compliance: list[Finding] = inputs.compliance_by.get(key, [])
    dismissed: list[Finding] = inputs.dismissed_by.get(key, [])
    entry: dict[str, Any] = {
        "principleId": key[1], "findings": len(findings), "compliance": len(compliance),
        "insufficient": True, "confidence": None, "files": inputs.source_file_count,
        "stages": None,
    }
    if not findings and not compliance:
        return entry
    rows = requirement_rows([finding_to_scoring_dict(f) for f in findings],
                            [finding_to_scoring_dict(c) for c in compliance],
                            [finding_to_scoring_dict(d) for d in dismissed])
    mass = principle_mass(rows, inputs.source_file_count, params=params)
    entry["insufficient"] = False
    entry["confidence"] = str(classify_confidence_level(
        len(findings), len(compliance), source_file_count=inputs.source_file_count))
    entry["stages"] = explain_principle(mass, params=params)
    return entry


def explain_dimension(
    reports_root: Path, project: str, run_id: str, dimension: str,
    params: ScoringParams | None = None,
) -> dict[str, Any]:
    """Per principle of *dimension* in *run_id*: the tallies and every stage
    of the score, computed from the same findings and parameters the grade
    tables use. Raises FileNotFoundError for an unknown run or dimension."""
    run_dir = _run_dir(reports_root, project, run_id)
    active = params if params is not None else load_params()
    inputs = load_grade_inputs(run_dir)
    keys = _keys_for(inputs, dimension)
    if not keys:
        raise DimensionNotFound(dimension)
    return {
        "runId": run_id,
        "dimension": dimension,
        "params": params_to_dict(active),
        "principles": [_explain_one(inputs, key, active) for key in keys],
    }
