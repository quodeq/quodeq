"""The scores payload names the grade formula version the numbers were computed with."""
from __future__ import annotations

from pathlib import Path

import quodeq.services.scoring as scoring
from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION


def test_an_empty_project_payload_carries_the_formula_version(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir(parents=True)
    payload = scoring.get_project_scores(tmp_path, "proj")
    assert payload is not None
    assert payload["scoring"]["formulaVersion"] == GRADE_ALGO_VERSION == 6


def test_a_project_with_runs_carries_the_formula_version(tmp_path: Path) -> None:
    (tmp_path / "proj" / "r1" / "evaluation").mkdir(parents=True)
    payload = scoring.get_project_scores(tmp_path, "proj")
    assert payload is not None
    assert payload["scoring"]["formulaVersion"] == GRADE_ALGO_VERSION
