"""Grade formula endpoints.

GET    /api/grade-formula          -- current + defaults + isCustom + rescore progress
PUT    /api/grade-formula          -- validate, save, start a background rescore (202)
DELETE /api/grade-formula          -- reset to Q2 defaults, start a background rescore (202)
POST   /api/grade-formula/preview  -- read-only before/after for one project
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import json_error
from quodeq.api.routes_common import reports_dir
from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    params_error,
    params_from_dict,
    params_to_dict,
    validate_params,
)
from quodeq.services import grade_formula
from quodeq.services.grade_formula_job import GradeFormulaRescorer, RescoreSnapshot
from quodeq.shared.validation import validate_path_segment


def _invalid_input(message: str) -> tuple[Response, int]:
    return json_error(message, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")


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


def _state_payload(rescore: RescoreSnapshot) -> dict:
    return {
        "current": params_to_dict(grade_formula.load_params()),
        "defaults": params_to_dict(DEFAULT_PARAMS),
        "isCustom": grade_formula.is_custom(),
        # Progress of the background rescore pass. The client polls GET
        # until appliedGeneration reaches the generation its PUT/DELETE got,
        # and warns when failed > 0: those runs keep the old formula.
        "rescore": rescore.to_payload(),
    }


def register_grade_formula_routes(
    app: Flask, rescorer: GradeFormulaRescorer | None = None,
) -> None:
    """Register grade formula endpoints.

    *rescorer* defaults to ``app.extensions["grade_formula_rescore"]``
    (``create_app`` puts one there); a bare test app gets a fresh one.
    """
    if rescorer is not None:
        app.extensions["grade_formula_rescore"] = rescorer
    job: GradeFormulaRescorer = app.extensions.setdefault(
        "grade_formula_rescore", GradeFormulaRescorer(),
    )

    @app.get("/api/grade-formula")
    def get_grade_formula() -> Response:
        return jsonify(_state_payload(job.snapshot()))

    @app.put("/api/grade-formula")
    def put_grade_formula() -> tuple[Response, int]:
        params, err = _parse_params(request.get_json(silent=True))
        if err:
            return err
        # Save first: a pass that starts after the generation bump loads these.
        grade_formula.save_params(params)
        snap = job.request(Path(reports_dir()))
        return jsonify(_state_payload(snap)), HTTPStatus.ACCEPTED

    @app.delete("/api/grade-formula")
    def delete_grade_formula() -> tuple[Response, int]:
        if request.args.get("confirm") != "true":
            return json_error(
                "Use ?confirm=true to confirm resetting the grade formula and rescoring every run",
                HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED",
            )
        grade_formula.reset_params()
        snap = job.request(Path(reports_dir()))
        return jsonify(_state_payload(snap)), HTTPStatus.ACCEPTED

    @app.post("/api/grade-formula/preview")
    def preview_grade_formula() -> Response | tuple[Response, int]:
        payload = request.get_json(silent=True) or {}
        project = payload.get("project") or ""
        try:
            validate_path_segment(project)
        except ValueError:
            return json_error(
                "Invalid project", HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
            )
        params, err = _parse_params(payload.get("params") or {})
        if err:
            return err
        result = grade_formula.preview_scores(Path(reports_dir()), project, params)
        if result is None:
            return json_error(
                "No evaluation with an event log found for this project",
                HTTPStatus.NOT_FOUND, "NOT_FOUND",
            )
        return jsonify(result)
