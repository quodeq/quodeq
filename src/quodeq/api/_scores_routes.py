"""Unified scoring API endpoints.

/api/projects/{project}/scores          -- full dashboard payload (accumulated + trend)
/api/projects/{project}/scores/{runId}  -- single run detail (for Explorer)
/api/projects/{project}/compliance-detail -- finding detail /scores and /scores/{runId} defer

All rescore logic happens server-side. The frontend never calls /api/rescore
directly when using these endpoints.
"""
from __future__ import annotations

import logging
import sqlite3
from http import HTTPStatus
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INTERNAL_ERROR, CODE_INVALID_INPUT, CODE_NOT_FOUND
from quodeq.api.helpers import json_error, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.core.types.finding_type import FindingType, parse_finding_type
from quodeq.services.scoring import get_project_scores, get_scores_raw, get_scores_slim
from quodeq.services.scoring.compliance_detail import defer_finding_detail, dimension_detail, finding_detail
from quodeq.services.warmup_defer import defer_to_warmup

_logger = logging.getLogger(__name__)

KIND_PARAM = "kind"
RUN_PARAM = "run"


def _load_scores(project: str) -> tuple[dict | None, tuple[Response, int] | None]:
    """The full payload, or an error."""
    as_of = request.args.get("asOf")
    eval_dir = reports_dir()
    try:
        result = get_project_scores(Path(eval_dir), project, as_of)
    except (OSError, sqlite3.Error, ValueError):
        _logger.exception("Unexpected error fetching scores for project %s", project)
        return None, json_error("Failed to load scores", HTTPStatus.INTERNAL_SERVER_ERROR, CODE_INTERNAL_ERROR)
    if result is None:
        return None, json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return result, None


@dataclass(frozen=True)
class _DetailScope:
    """What a ``/compliance-detail`` request asks for."""
    dimension: str
    kind: FindingType
    run_id: str | None
    filters: dict[str, str | None]


def _detail_scope() -> _DetailScope | tuple[Response, int]:
    """The dimension, kind, run and item filters of a detail request, or an error."""
    dimension = request.args.get("dimension")
    if not dimension:
        return json_error("dimension is required", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
    run_id = request.args.get(RUN_PARAM) or None
    err = validate_segment(*(seg for seg in (dimension, run_id) if seg))
    if err:
        return err
    # ``kind`` picks the list to refill; compliance is the pre-kind default
    # so existing callers keep working.
    raw_kind = request.args.get(KIND_PARAM)
    kind = FindingType.COMPLIANCE if not raw_kind else parse_finding_type(raw_kind)
    if kind is None:
        return json_error(
            f"{KIND_PARAM} must be one of {[k.value for k in FindingType]}, got {raw_kind!r}",
            HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT,
        )
    filters = {"principle": request.args.get("principle"), "path_prefix": request.args.get("pathPrefix")}
    return _DetailScope(dimension, kind, run_id, filters)


def _run_dimensions(eval_root: Path, project: str, run_id: str) -> tuple[list | None, tuple[Response, int] | None]:
    """One run's rescored dimensions (the lists ``/scores/<run>`` defers), or an error."""
    try:
        return get_scores_raw(eval_root, project, run_id)["dimensions"], None
    except FileNotFoundError:
        return None, json_error("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    except (OSError, sqlite3.Error, ValueError):
        _logger.exception("Unexpected error fetching run scores for project %s run %s", project, run_id)
        return None, json_error("could not read run scores", HTTPStatus.INTERNAL_SERVER_ERROR, "SCORES_READ_FAILED")


def finding_detail_response(
    project: str, load_scores: Callable[[], tuple[dict | None, tuple[Response, int] | None]],
    eval_root: Path | None = None,
) -> Response | tuple[Response, int]:
    """The ``/compliance-detail`` body: full items of one kind in one dimension.

    ``?run=`` refills the lists ``/scores/<run>`` deferred for that run;
    otherwise the accumulated lists of *load_scores*' payload (``?asOf=``
    included). Shared by the local route and its shared mirror.
    """
    err = validate_segment(project)
    if err:
        return err
    scope = _detail_scope()
    if not isinstance(scope, _DetailScope):
        return scope
    if scope.run_id:
        dims, err = _run_dimensions(eval_root or Path(reports_dir()), project, scope.run_id)
        if err:
            return err
        return jsonify({"items": dimension_detail(dims, scope.dimension, scope.kind, **scope.filters)})
    loaded, err = load_scores()
    if err:
        return err
    return jsonify({"items": finding_detail(loaded, scope.dimension, scope.kind, **scope.filters)})


def register_scores_routes(app: Flask) -> None:
    """Register unified scoring endpoints."""

    @app.get("/api/projects/<project>/scores")
    def project_scores(project: str) -> Response | tuple[Response, int]:
        err = validate_segment(project)
        if err:
            return err
        # While the warm-up still owes this project its caches, the client
        # polls a pending body instead of this request building the payload
        # inline beside the worker (see defer_to_warmup).
        deferred = defer_to_warmup(reports_dir(), project)
        if deferred is not None:
            return jsonify(deferred), HTTPStatus.ACCEPTED
        loaded, err = _load_scores(project)
        if err:
            return err
        # The service memoizes the payload itself; ``defer_finding_detail``
        # copies what it strips, so the memoized dict is never mutated.
        return jsonify(defer_finding_detail(loaded))

    @app.get("/api/projects/<project>/scores/<run_id>")
    def project_run_scores(project: str, run_id: str) -> Response | tuple[Response, int]:
        err = validate_segment(project, run_id)
        if err:
            return err
        eval_dir = reports_dir()
        try:
            result = get_scores_slim(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            return json_error("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        except (OSError, sqlite3.Error, ValueError):
            _logger.exception("Unexpected error fetching run scores for project %s run %s", project, run_id)
            return json_error(
                "could not read run scores", HTTPStatus.INTERNAL_SERVER_ERROR, "SCORES_READ_FAILED"
            )
        return jsonify(result)

    _register_compliance_detail_route(app)


def _register_compliance_detail_route(app: Flask) -> None:
    @app.get("/api/projects/<project>/compliance-detail")
    def project_compliance_detail(project: str) -> Response | tuple[Response, int]:
        return finding_detail_response(project, lambda: _load_scores(project))
