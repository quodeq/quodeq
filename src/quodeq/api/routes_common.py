"""Shared helpers used across route modules."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, request

from quodeq.shared.utils import get_evaluations_dir


def reports_dir() -> str:
    """Resolve the reports directory from server configuration.

    Takes no request input, deliberately. This used to accept an
    ``?evaluations=`` query parameter that repointed the entire reports root,
    guarded by a containment check against the configured directory. No
    client, test, or documented workflow ever sent it: every one of the 36
    call sites invokes ``reports_dir()`` bare. An unused parameter that
    redirects the storage root is attack surface with no upside, so it is
    gone rather than guarded.

    The consequence worth knowing: this value is now server-controlled, so
    every path built on top of it starts from a trusted root. Do not
    reintroduce a request-supplied override here. If a future feature needs
    multiple roots, resolve them from configuration and select by an opaque
    identifier, never by a caller-supplied path.
    """
    return os.path.realpath(get_evaluations_dir())


def standards_compiled_dir(app: Flask) -> Path:
    """The compiled-standards directory ``create_app`` configured on *app*."""
    return Path(app.config["STANDARDS_COMPILED_DIR"])


LOCALHOST_ADDRS = frozenset({"127.0.0.1", "::1"})


def is_local_request() -> bool:
    """True when the current request comes from a loopback address."""
    return (request.remote_addr or "") in LOCALHOST_ADDRS


def sync_block(snapshot: dict) -> dict:
    """camelCase one job slot for the wire."""
    out = dict(snapshot)
    out["finishedAt"] = out.pop("finished_at", None)
    out["projectsFound"] = out.pop("projects_found", None)
    if "project_id" in out:
        out["projectId"] = out.pop("project_id")
        out["projectName"] = out.pop("project_name", None)
    if "scan_data" in out:
        out["scanData"] = out.pop("scan_data")
    if "source_project_id" in out:
        out["sourceProjectId"] = out.pop("source_project_id")
        out["conflictKind"] = out.pop("conflict_kind", None)
    return out
