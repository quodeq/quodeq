"""Read-only mirrors of the dismissed/verified findings listings, scoped to the shared clone.

Split out of routes_shared_mirrors.py to keep that module under the size
limit. Same read-only invariant: nothing here mutates a finding.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from flask import Flask, jsonify, request

from quodeq.api.helpers import page_params
from quodeq.services._dismissed_listing import load_dismissed
from quodeq.services.verified import verified_entries

from .routes_shared_common import _shared_project_dir, _validate_segment, _with_shared_root

# Mirrors quodeq.api.routes_findings._MAX_FINDINGS_LIST_LIMIT — the shared
# findings mirrors clamp to the same hard cap as the local routes.
_MAX_FINDINGS_LIST_LIMIT = 5000


def _shared_findings_page(project: str, eval_root: Path, lister: Callable[..., list]):
    """Shared body of the dismissed/verified mirrors: validate, resolve, clamp, list."""
    err = _validate_segment(project)
    if err:
        return err
    project_dir = _shared_project_dir(eval_root, project)
    if project_dir is None:
        return jsonify([])
    paging = page_params(request.args, default_limit=_MAX_FINDINGS_LIST_LIMIT)
    if isinstance(paging[0], dict):
        return paging
    limit, offset = paging
    limit = min(limit, _MAX_FINDINGS_LIST_LIMIT)
    return jsonify(lister(project_dir, offset=offset, limit=limit))


# The local routes take ``project`` as a query param
# (``/api/findings/dismissed?project=``) since /api/findings/* is a flat
# namespace shared by mutation routes too. Every other shared mirror
# nests ``project`` as a URL path segment, so these two follow that
# convention instead of the local route's exact URL shape -- the response
# bodies (bare JSON array, same item shape) are unchanged.
@_with_shared_root
def shared_dismissed_findings(project: str, eval_root: Path):
    """List the findings dismissed in the shared clone, as a bare JSON array."""
    return _shared_findings_page(project, eval_root, load_dismissed)


@_with_shared_root
def shared_verified_findings(project: str, eval_root: Path):
    """List the findings verified in the shared clone, as a bare JSON array."""
    return _shared_findings_page(project, eval_root, verified_entries)


def register_shared_findings_mirror_routes(app: Flask) -> None:
    """Bind the two shared findings-listing mirrors. Called from routes_shared_mirrors."""
    app.get("/api/shared/projects/<project>/findings/dismissed")(shared_dismissed_findings)
    app.get("/api/shared/projects/<project>/findings/verified")(shared_verified_findings)
