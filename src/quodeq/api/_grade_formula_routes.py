"""Grade formula endpoints.

GET    /api/grade-formula          -- current + defaults + isCustom
PUT    /api/grade-formula          -- validate, save, rescore all runs
DELETE /api/grade-formula          -- reset to Q2 defaults, rescore all runs
POST   /api/grade-formula/preview  -- read-only before/after for one project
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    params_from_dict,
    params_to_dict,
    validate_params,
)
from quodeq.services import grade_formula
from quodeq.shared.validation import validate_path_segment


def _parse_params(data: dict) -> tuple:
    """Returns (params, None) or (None, (response, status)) on validation error."""
    try:
        params = params_from_dict(data or {})
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        body, status = error_response(
            f"Malformed params: {exc}", HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
        return None, (jsonify(body), status)
    errors = validate_params(params)
    if errors:
        body, status = error_response(
            "; ".join(errors), HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
        return None, (jsonify(body), status)
    return params, None


def _state_payload(applied: int | None = None) -> dict:
    payload = {
        "current": params_to_dict(grade_formula.load_params()),
        "defaults": params_to_dict(DEFAULT_PARAMS),
        "isCustom": grade_formula.is_custom(),
    }
    if applied is not None:
        payload["applied"] = applied
    return payload


def register_grade_formula_routes(app: Flask) -> None:
    """Register grade formula endpoints."""

    @app.get("/api/grade-formula")
    def get_grade_formula() -> Response:
        return jsonify(_state_payload())

    @app.put("/api/grade-formula")
    def put_grade_formula() -> Response | tuple[Response, int]:
        params, err = _parse_params(request.get_json(silent=True))
        if err:
            return err
        grade_formula.save_params(params)
        applied = grade_formula.apply_to_all_runs(Path(reports_dir()))
        return jsonify(_state_payload(applied=applied))

    @app.delete("/api/grade-formula")
    def delete_grade_formula() -> Response:
        grade_formula.reset_params()
        applied = grade_formula.apply_to_all_runs(Path(reports_dir()))
        return jsonify(_state_payload(applied=applied))

    @app.post("/api/grade-formula/preview")
    def preview_grade_formula() -> Response | tuple[Response, int]:
        payload = request.get_json(silent=True) or {}
        project = payload.get("project") or ""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response(
                "Invalid project", HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
            )
            return jsonify(body), status
        params, err = _parse_params(payload.get("params") or {})
        if err:
            return err
        result = grade_formula.preview_scores(Path(reports_dir()), project, params)
        if result is None:
            body, status = error_response(
                "No evaluation with an event log found for this project",
                HTTPStatus.NOT_FOUND, "NOT_FOUND",
            )
            return jsonify(body), status
        return jsonify(result)
