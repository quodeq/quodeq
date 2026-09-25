"""Wire shaping for GET .../dimensions/<dimension>/eval, shared by the local
project route and its /api/shared mirror.

``services.fs_reports.get_dimension_eval`` returns whichever shape the
dimension's evidence is currently in: a ``ViolationResponse`` while the run
is still writing evidence, a stored camelCase dict once
``evaluation/<dim>.json`` exists, an ``EvalPending`` marker while the run
directory exists but nothing has landed yet, or ``None`` when the run itself
doesn't exist. This is the one place that turns that union into the wire
body both routes send.
"""
from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import Response, jsonify

from quodeq.api._constants import CODE_NOT_FOUND
from quodeq.api.helpers import json_error
from quodeq.core.types import EvalPending, ViolationResponse
from quodeq.shared.serialization import to_camel_dict


def dimension_eval_response(
    payload: ViolationResponse | dict[str, Any] | EvalPending | None,
) -> Response | tuple[Response, int]:
    """The response for one dimension's evaluation, local or shared.

    404 when there is no evaluation file, 202 with the waiting body while
    the dimension is still being written (``EvalPending``) so the UI keeps
    polling, else the payload.
    """
    if payload is None:
        return json_error("Eval file not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    if isinstance(payload, EvalPending):
        body = {"waiting": True, **to_camel_dict(payload)}
        return jsonify(body), HTTPStatus.ACCEPTED
    return jsonify(to_camel_dict(payload))
