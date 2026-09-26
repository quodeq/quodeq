"""Project dashboard, accumulated, evaluation, and violation routes."""
from __future__ import annotations

from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_INPUT, CODE_NOT_FOUND
from quodeq.api.dimension_eval_wire import dimension_eval_response
from quodeq.api.helpers import json_error
from quodeq.api.routes_common import reports_dir
from quodeq.shared.serialization import to_camel_dict
from quodeq.services.base import ActionProvider
from quodeq.services.run_constants import LATEST_RUN
from quodeq.shared.validation import validate_path_segment


def _validate_params(**params: str) -> tuple[Response, int] | None:
    """Validate each named route parameter one at a time, so the first
    invalid one names itself in the error message instead of a generic
    "Invalid parameter"."""
    for name, value in params.items():
        try:
            validate_path_segment(value)
        except ValueError:
            return json_error(
                f"{name} must be a plain path segment, got {value!r}",
                HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT,
            )
    return None


def register_project_data_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project dashboard, accumulated, evaluation, and violation routes."""

    @app.get("/api/projects/<project>/dashboard")
    def dashboard(project: str) -> Response | tuple[Response, int]:
        err = _validate_params(project=project)
        if err:
            return err
        run = request.args.get("run", LATEST_RUN)
        try:
            payload = provider.get_dashboard(reports_dir(), project, run)
        except FileNotFoundError:
            return json_error("Dashboard data not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        return jsonify(payload)

    @app.get("/api/projects/<project>/accumulated")
    def accumulated(project: str) -> Response | tuple[Response, int]:
        err = _validate_params(project=project)
        if err:
            return err
        as_of = request.args.get("asOf")
        payload = provider.get_accumulated(reports_dir(), project, as_of)
        if payload is None:
            return json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval")
    def dimension_eval(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
        err = _validate_params(project=project, run_id=run_id, dimension=dimension)
        if err:
            return err
        return dimension_eval_response(provider.get_dimension_eval(reports_dir(), project, run_id, dimension))

    @app.get("/api/projects/<project>/runs/<run_id>/violations")
    def run_violations(project: str, run_id: str) -> Response | tuple[Response, int]:
        err = _validate_params(project=project, run_id=run_id)
        if err:
            return err
        try:
            payload = provider.get_violations(reports_dir(), project, run_id)
        except FileNotFoundError:
            return json_error("Violation data not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        return jsonify(to_camel_dict(payload))
