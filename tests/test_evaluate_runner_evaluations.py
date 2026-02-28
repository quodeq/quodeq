from pathlib import Path

import pytest

from codecompass.evaluate.runner import EvaluateConfig, ensure_reports_dir


def test_ensure_reports_dir_default_creates(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    ensure_reports_dir(reports_dir, reports_defaulted=True)
    assert reports_dir.exists()


def test_ensure_reports_dir_custom_missing_errors(tmp_path: Path):
    reports_dir = tmp_path / "missing"
    with pytest.raises(FileNotFoundError) as excinfo:
        ensure_reports_dir(reports_dir, reports_defaulted=False)
    message = str(excinfo.value)
    assert "Reports directory not found" in message
    assert "mkdir -p" in message
    assert "omit --reports" in message
