"""Shared fixtures for tests/services/test_grade_formula_*.py siblings.

Split out of test_grade_formula.py.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setenv("QUODEQ_GRADE_FORMULA_PATH", str(path))
    return path
