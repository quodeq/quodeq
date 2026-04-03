"""Project dashboard, accumulated, evaluation, and violation routes."""
from __future__ import annotations

from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.core.types import to_camel_dict
from quodeq.services.base import ActionProvider


def register_project_data_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project dashboard, accumulated, evaluation, and violation routes."""

    @app.get("/api/projects/<project>/dashboard")
    def dashboard(project: str) -> Response | tuple[Response, int]:
        run = request.args.get("run", "latest")
        try:
            payload = provider.get_dashboard(reports_dir(), project, run)
        except FileNotFoundError:
            body, status = error_response("Dashboard data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/accumulated")
    def accumulated(project: str) -> Response | tuple[Response, int]:
        as_of = request.args.get("asOf")
        payload = provider.get_accumulated(reports_dir(), project, as_of)
        if payload is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval")
    def dimension_eval(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
        payload = provider.get_dimension_eval(reports_dir(), project, run_id, dimension)
        if payload is None:
            body, status = error_response("Eval file not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        if payload.get("waiting"):
            return jsonify(payload), HTTPStatus.ACCEPTED
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/violations")
    def run_violations(project: str, run_id: str) -> Response | tuple[Response, int]:
        try:
            payload = provider.get_violations(reports_dir(), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Violation data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(payload))
