"""Persistence for user-tuned grade formula parameters.

The file at ``~/.quodeq/grade_formula.json`` holds the camelCase dict shape
from ``params_to_dict``. Absent file means Q² defaults. A corrupt file logs
a warning and falls back to defaults rather than breaking every score read.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    ScoringParams,
    params_from_dict,
    params_to_dict,
    validate_params,
)

_logger = logging.getLogger(__name__)


def grade_formula_path() -> Path:
    """Location of the custom-params file (function so tests can monkeypatch)."""
    return Path.home() / ".quodeq" / "grade_formula.json"


def load_params() -> ScoringParams:
    """Return saved custom params, or Q² defaults when absent or unreadable."""
    path = grade_formula_path()
    if not path.is_file():
        return DEFAULT_PARAMS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = params_from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        _logger.warning("Unreadable %s (%s); using Q2 default formula.", path, exc)
        return DEFAULT_PARAMS
    if validate_params(params):
        _logger.warning("Invalid params in %s; using Q2 default formula.", path)
        return DEFAULT_PARAMS
    return params


def save_params(params: ScoringParams) -> None:
    """Validate and persist custom params. Raises ValueError when invalid."""
    errors = validate_params(params)
    if errors:
        raise ValueError("; ".join(errors))
    path = grade_formula_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params_to_dict(params), indent=2), encoding="utf-8")


def reset_params() -> None:
    """Remove the custom-params file (back to Q² defaults)."""
    grade_formula_path().unlink(missing_ok=True)


def is_custom() -> bool:
    """True when a custom-params file is in effect."""
    return grade_formula_path().is_file()
