"""The dashboard payload must say when the grade came from a tuned formula.

A hand-edited grade formula moves every score in the project at once and
leaves no other trace: findings do not change, runs do not change, only the
number does. Setting `severityWeight.major` to 6.0 (the shipped default is
1.5) cost this project roughly a point across every dimension for a month,
and nothing on the Overview -- where the grade is actually read -- said the
formula was no longer stock. `isCustom` existed, but only on the grade-formula
settings page, which is the one place you already know.
"""
from __future__ import annotations

from pathlib import Path

import quodeq.services.scoring as scoring
from quodeq.services.scoring._deps import ScoringDeps


def _run_dir(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id / "evaluation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_payload_flags_a_tuned_formula(tmp_path):
    _run_dir(tmp_path, "proj", "r1")
    deps = ScoringDeps(is_custom_formula=lambda: True)

    payload = scoring.get_project_scores(tmp_path, "proj", deps=deps)

    assert payload is not None
    assert payload["scoring"]["customFormula"] is True


def test_payload_reports_stock_formula_as_not_custom(tmp_path):
    _run_dir(tmp_path, "proj", "r1")
    deps = ScoringDeps(is_custom_formula=lambda: False)

    payload = scoring.get_project_scores(tmp_path, "proj", deps=deps)

    assert payload is not None
    assert payload["scoring"]["customFormula"] is False


def test_flag_is_present_even_when_the_project_has_no_runs(tmp_path):
    """The empty-project early return is a separate exit -- it needs the flag too,
    or the Overview silently loses the warning exactly when a first scan lands."""
    (tmp_path / "proj").mkdir(parents=True)
    deps = ScoringDeps(is_custom_formula=lambda: True)

    payload = scoring.get_project_scores(tmp_path, "proj", deps=deps)

    assert payload is not None
    assert payload["scoring"]["customFormula"] is True
