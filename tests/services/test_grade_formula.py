"""Tests for grade-formula params persistence."""
from __future__ import annotations

import dataclasses

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services import grade_formula


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setattr(grade_formula, "grade_formula_path", lambda: path)
    return path


def test_load_returns_defaults_when_file_absent(formula_path):
    assert grade_formula.load_params() == DEFAULT_PARAMS
    assert grade_formula.is_custom() is False


def test_save_then_load_round_trips(formula_path):
    custom = dataclasses.replace(DEFAULT_PARAMS, base_k=0.3)
    grade_formula.save_params(custom)
    assert formula_path.is_file()
    assert grade_formula.load_params() == custom
    assert grade_formula.is_custom() is True


def test_load_falls_back_to_defaults_on_corrupt_file(formula_path):
    formula_path.write_text("{not json")
    assert grade_formula.load_params() == DEFAULT_PARAMS


def test_reset_removes_file(formula_path):
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    grade_formula.reset_params()
    assert not formula_path.exists()
    assert grade_formula.is_custom() is False


def test_save_rejects_invalid_params(formula_path):
    bad = dataclasses.replace(DEFAULT_PARAMS, base_k=99.0)
    with pytest.raises(ValueError):
        grade_formula.save_params(bad)
    assert not formula_path.exists()


@pytest.mark.parametrize("payload", [
    "[1, 2, 3]",
    "null",
    '{"severityWeight": "oops"}',
    '{"severityWeight": [1, 2]}',
])
def test_load_falls_back_on_wrong_shape_json(formula_path, payload):
    formula_path.write_text(payload)
    assert grade_formula.load_params() == DEFAULT_PARAMS
