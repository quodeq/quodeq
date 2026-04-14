"""Shared helpers used across route modules."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import abort, jsonify, make_response, request

from quodeq.shared.utils import get_evaluations_dir


def reports_dir(default_path: str | None = None, request_args: dict | None = None) -> str:
    """Resolve the reports directory from query params or *default_path*.

    *request_args* overrides ``request.args`` when provided, allowing the
    function to be called without a live Flask request context (e.g. in tests).
    """
    fallback = default_path if default_path is not None else get_evaluations_dir()
    args = request_args if request_args is not None else request.args
    raw = args.get("evaluations") or fallback
    resolved = Path(raw).resolve()
    default_resolved = Path(fallback).resolve()
    if not resolved.is_relative_to(default_resolved):
        response = make_response(
            jsonify({"error": "Access denied: path is outside the allowed directory", "code": "FORBIDDEN"}),
            HTTPStatus.FORBIDDEN,
        )
        abort(response)
    return str(resolved)
