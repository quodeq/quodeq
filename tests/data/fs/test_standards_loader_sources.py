"""Compiled standards win over custom evaluators; only a corrupt compiled file warns."""
from __future__ import annotations

import json
import logging

import pytest

from quodeq.data.fs.standards_loader import load_compiled_requirements

_LOGGER = "quodeq.data.fs.standards_loader"
_STANDARD = {"principles": [{"name": "P", "requirements": [{"id": "R-1", "text": "t"}]}]}


@pytest.fixture
def dirs(tmp_path):
    compiled, evaluators = tmp_path / "compiled", tmp_path / "evaluators"
    compiled.mkdir()
    evaluators.mkdir()
    return compiled, evaluators


def _load(compiled, evaluators):
    return load_compiled_requirements(compiled, "sec", evaluators_dir=evaluators)


def test_a_custom_evaluator_is_read_when_no_compiled_file_exists(dirs):
    compiled, evaluators = dirs
    (evaluators / "sec.json").write_text(json.dumps(_STANDARD), encoding="utf-8")
    assert set(_load(compiled, evaluators)) == {"R-1"}


def test_a_corrupt_compiled_file_warns_and_does_not_fall_back(dirs, caplog):
    compiled, evaluators = dirs
    (compiled / "sec.json").write_text("{", encoding="utf-8")
    (evaluators / "sec.json").write_text(json.dumps(_STANDARD), encoding="utf-8")
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    assert _load(compiled, evaluators) == {}
    assert [r.getMessage().split(":")[0] for r in caplog.records] == [
        "Failed to load compiled standards for sec",
    ]


def test_a_corrupt_custom_evaluator_is_skipped_silently(dirs, caplog):
    compiled, evaluators = dirs
    (evaluators / "sec.json").write_text("{", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    assert _load(compiled, evaluators) == {}
    assert caplog.records == []
