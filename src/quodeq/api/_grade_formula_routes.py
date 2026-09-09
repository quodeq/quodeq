"""Grade formula endpoints.

GET    /api/grade-formula          -- current + defaults + isCustom
PUT    /api/grade-formula          -- validate, save, rescore all runs
DELETE /api/grade-formula          -- reset to Q2 defaults, rescore all runs
POST   /api/grade-formula/preview  -- read-only before/after for one project
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    params_error,
    params_from_dict,
    params_to_dict,
    validate_params,
)
from quodeq.services import grade_formula
from quodeq.shared.validation import validate_path_segment


def _invalid_input(message: str) -> tuple[Response, int]:
    body, status = error_response(message, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    return jsonify(body), status


def _parse_params(data: dict) -> tuple:
    """Returns (params, None) or (None, (response, status)) on validation error."""
    err = params_error(data or {})
    if err is not None:
        return None, _invalid_input(err)
    try:
        params = params_from_dict(data or {})
    except (TypeError, ValueError, KeyError, AttributeError):
        # Unreachable once params_error passed; kept as a safety net with a
        # constant message so nothing here can ever echo exception text.
        return None, _invalid_input("Malformed params")
    errors = validate_params(params)
    if errors:
        return None, _invalid_input("; ".join(errors))
    return params, None


def _state_payload(result: "grade_formula.ApplyResult | None" = None) -> dict:
    payload = {
        "current": params_to_dict(grade_formula.load_params()),
        "defaults": params_to_dict(DEFAULT_PARAMS),
        "isCustom": grade_formula.is_custom(),
    }
    if result is not None:
        payload["applied"] = result.rescored
        # Surface a partial apply so the client can warn that some runs still
        # show the old formula, instead of the endpoint claiming full success.
        payload["failed"] = len(result.failed)
    return payload


def register_grade_formula_routes(
    app: Flask,
    apply_to_all_runs: Callable[[Path], grade_formula.ApplyResult] = grade_formula.apply_to_all_runs,
) -> None:
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
        result = apply_to_all_runs(Path(reports_dir()))
        return jsonify(_state_payload(result=result))

    @app.delete("/api/grade-formula")
    def delete_grade_formula() -> Response:
        grade_formula.reset_params()
        result = apply_to_all_runs(Path(reports_dir()))
        return jsonify(_state_payload(result=result))

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
