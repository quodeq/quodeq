"""GET /api/projects/<project>/runs/<run_id>/dimensions/<dimension>/explain."""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify

from quodeq.api._constants import CODE_INTERNAL_ERROR, CODE_INVALID_PARAM, CODE_NOT_FOUND
from quodeq.api._http_cache import conditional_json
from quodeq.api._grade_formula_routes import parse_params
from quodeq.api.helpers import json_error, optional_json_object_or_response, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.core.scoring.params import ScoringParams
from quodeq.services.grade_explain import DimensionNotFound, explain_dimension

_logger = logging.getLogger(__name__)
_ROUTE = "/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/explain"


def _explain(project: str, run_id: str, dimension: str, params: ScoringParams | None) -> dict | tuple[Response, int]:
    """The explain payload, or the error response for a missing run or dimension."""
    try:
        return explain_dimension(Path(reports_dir()), project, run_id, dimension, params)
    except DimensionNotFound:
        return json_error("Dimension not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    except FileNotFoundError:
        return json_error("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    except (OSError, ValueError):
        _logger.exception("Failed to explain %s of run %s for %s", dimension, run_id, project)
        return json_error("Failed to explain the grade", HTTPStatus.INTERNAL_SERVER_ERROR, CODE_INTERNAL_ERROR)


def grade_explain(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
    """The score stages per principle with the stored parameters."""
    err = validate_segment(project, run_id, dimension)
    if err is not None:
        return err
    result = _explain(project, run_id, dimension, None)
    return result if isinstance(result, tuple) else conditional_json(result, max_age=0)


def grade_explain_draft(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
    """The same stages computed with the draft parameters in the body
    (``{"params": {...}}``, the preview route's shape), so the editor can
    show the effect of a knob before it is applied."""
    err = validate_segment(project, run_id, dimension)
    if err is not None:
        return err
    body = optional_json_object_or_response(CODE_INVALID_PARAM)
    if not isinstance(body, dict):
        return body
    params, param_err = parse_params(body.get("params") or {})
    if param_err is not None:
        return param_err
    result = _explain(project, run_id, dimension, params)
    return result if isinstance(result, tuple) else jsonify(result)


def register_grade_explain_routes(app: Flask) -> None:
    """Bind the explain routes."""
    app.get(_ROUTE)(grade_explain)
    app.post(_ROUTE)(grade_explain_draft)
