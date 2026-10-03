"""What the fleet compare routes share: the ``projects`` query parsing and the failure sink.

Used by the local route (:mod:`routes_compare`) and its shared-root mirror
(:mod:`routes_shared_mirrors`), which otherwise differ only in the root they
build from.
"""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Response, request

from quodeq.api._constants import CODE_INVALID_INPUT
from quodeq.api.helpers import json_error, validate_segment
from quodeq.shared.log_sink import LoggerSink

#: The sink the fleet builder reports per-project failures through.
FLEET_LOG = LoggerSink(logging.getLogger(__name__))

FLEET_PROJECTS_ARG = "projects"


def fleet_projects_or_error() -> list[str] | tuple[Response, int]:
    """The ``projects`` query list (comma separated, blanks dropped), or a coded 400.

    Every name is checked as a path segment before any filesystem access;
    an empty list is a 400 too, since a fleet request without projects is a
    client error rather than an empty fleet.
    """
    names = [n.strip() for n in request.args.get(FLEET_PROJECTS_ARG, "").split(",")]
    names = [n for n in names if n]
    if not names:
        return json_error(f"{FLEET_PROJECTS_ARG} is required", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
    err = validate_segment(*names, message="Invalid project name")
    return err if err is not None else names
