"""Shared helpers for the ``/api/shared/*`` route modules.

``with_shared_root`` and ``validate_segment`` are used by the config, pull,
and read-only mirror route registrars alike; ``shared_project_dir`` by the
pull route and two of the mirrors. Split out of routes_shared.py so
those registrars can share one implementation instead of three copies.
"""
from __future__ import annotations

import functools
import inspect
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Response

from quodeq.api.helpers import json_error
from quodeq.services.score_cache import score_cache_path_override
from quodeq.services.shared_repo import (
    read_state,
    shared_evaluations_root,
    shared_score_cache_path,
)
from quodeq.services.shared_settings import read_settings
from quodeq.shared.validation import resolve_child_dir, validate_path_segment

logger = logging.getLogger(__name__)


def with_shared_root(fn):
    """Resolve the configured clone; inject eval_root; scope the score cache.

    Every decorated route becomes: 409 when unconfigured, 409 when the
    clone's format is foreign or newer than this build understands, 503 when
    the clone hasn't been fetched yet at all, else the wrapped view runs with
    ``eval_root`` (the shared clone's evaluations directory) injected as a
    keyword argument, with the score cache transparently scoped to this
    clone's own cache DB so its rows never mix with the local
    clone's cache. Views that also declare a ``url`` parameter get the
    configured remote; the rest are not handed one.

    "ok" and "empty" (cloned, never published into) both proceed: an empty
    clone is a legitimate first-connect state, not an error, and every
    wrapped list-shaped route already tolerates a missing evaluations dir by
    returning an empty result (see build_project_list) rather than raising.
    """

    wants_url = "url" in inspect.signature(fn).parameters

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        settings = read_settings()
        if not settings.url:
            return json_error(
                "no shared repository configured", HTTPStatus.CONFLICT, "NO_SHARED_REPO"
            )
        state = read_state(settings.url)
        if state == "unsupported_version":
            return json_error(
                "this shared repository requires a newer version of quodeq",
                HTTPStatus.CONFLICT,
                "UNSUPPORTED_VERSION",
            )
        if state == "foreign":
            return json_error(
                "the configured repository does not look like a quodeq results repository"
                " — reconnect it in Settings",
                HTTPStatus.CONFLICT,
                "FOREIGN_REPO",
            )
        if state == "missing":
            return json_error(
                "the shared repository has not been cloned yet — reconnect it in Settings",
                HTTPStatus.SERVICE_UNAVAILABLE,
                "SHARED_REPO_MISSING",
            )
        root = shared_evaluations_root(settings.url)
        injected = {"eval_root": root}
        if wants_url:
            injected["url"] = settings.url
        with score_cache_path_override(shared_score_cache_path(settings.url)):
            return fn(*args, **injected, **kwargs)

    return wrapper


def validate_segment(*segments: str) -> tuple[Response, int] | None:
    """Shared-route path-segment guard.

    Every shared mirror that takes a project/run/dimension segment validates
    it here, even where the local route it mirrors relies solely on the
    service layer's own traversal check — defense in depth for a surface
    that serves a second, independently-controlled clone.
    """
    try:
        validate_path_segment(*segments)
    except ValueError:
        return json_error("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    return None


def shared_project_dir(eval_root: Path, project: str) -> Path | None:
    """Resolve *project* under *eval_root* by listing; None if there is no such entry.

    *project* is matched against real directory entries rather than joined onto
    *eval_root*, so a hostile value matches nothing instead of needing to be
    contained afterwards. None means absent, not invalid: callers run
    validate_segment first, so a bad name is already a 400 by this point.
    """
    resolved = resolve_child_dir(eval_root, project)
    return Path(resolved) if resolved is not None else None
