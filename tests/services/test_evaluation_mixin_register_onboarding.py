"""Tests for evaluation_mixin.py — start_evaluation onboarding-completed stamp.

Split from test_evaluation_mixin_register.py. Shared fixture (_FakeDispatcher /
_make_mixin) lives in tests/services/_evaluation_fixtures.py.
"""
import json
from pathlib import Path

from quodeq.services.project_registration import register_project as _register_project
from tests.services._evaluation_fixtures import _make_mixin


def _read_info(reports_root: Path, uuid: str) -> dict:
    return json.loads((reports_root / uuid / "repository_info.json").read_text())


def test_start_evaluation_stamps_onboarding_completed(tmp_path):
    """Starting an evaluation completes onboarding: the null field written at
    registration time must become a timestamp, otherwise the Projects page
    shows 'Resume setup' forever for wizard-created projects."""
    from quodeq.services.base import EvaluationOptions

    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()
    uuid = _register_project(str(repo), None, str(reports))
    assert _read_info(reports, uuid)["onboardingCompletedAt"] is None

    _make_mixin().start_evaluation(str(repo), str(reports), EvaluationOptions())

    stamped = _read_info(reports, uuid)["onboardingCompletedAt"]
    assert isinstance(stamped, str) and stamped


def test_start_evaluation_preserves_existing_onboarding_stamp(tmp_path):
    """A later evaluation must not move an already-set completion timestamp."""
    from quodeq.services.base import EvaluationOptions

    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()
    uuid = _register_project(str(repo), None, str(reports))
    info_path = reports / uuid / "repository_info.json"
    data = json.loads(info_path.read_text())
    data["onboardingCompletedAt"] = "2025-12-01T00:00:00Z"
    info_path.write_text(json.dumps(data))

    _make_mixin().start_evaluation(str(repo), str(reports), EvaluationOptions())

    assert _read_info(reports, uuid)["onboardingCompletedAt"] == "2025-12-01T00:00:00Z"
