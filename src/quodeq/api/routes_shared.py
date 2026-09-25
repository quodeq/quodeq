"""Routes for the shared results repository (config, status, refresh, publish),
plus read-only mirrors of the project read endpoints scoped to the shared clone.

Read-only invariant: no finding-mutation routes exist in this module or
anywhere under /api/shared/*. Every ``/api/shared/projects/...`` route is a
thin GET-only delegation to the same service functions the local
``/api/projects/...`` routes use, pointed at the shared clone's evaluations
root (via ``with_shared_root``) instead of the local reports directory.

A thin orchestrator over four modules:
  - routes_shared_common.py: ``with_shared_root``, ``shared_project_dir``
    and ``no_shared_repo_error``, shared by the three registrars below.
  - routes_shared_config.py: status / config PUT-DELETE / refresh / publish.
    Owns the ``refresh_shared_clone`` / ``start_publish`` imports used by
    its own routes.
  - routes_shared_pull.py: the one write exception to the read-only
    invariant (materializing a shared project as a local copy).
  - routes_shared_mirrors.py: the read-only mirrors of the project routes.
    Owns the ``refresh_shared_clone`` / ``sync_shared_index`` imports used
    by its own routes.

This module holds no patch-holder re-exports: each split registrar imports
its own dependencies directly from their real owners, so tests patch the
module that actually calls the name (see each split module's docstring).
"""
from __future__ import annotations

from flask import Flask

from .routes_shared_common import (  # noqa: F401 — re-export
    logger,
    shared_project_dir,
    with_shared_root,
)
from .routes_shared_config import register_shared_config_routes
from .routes_shared_pull import register_shared_pull_routes
from .routes_shared_mirrors import register_shared_mirror_routes


def register_shared_routes(app: Flask) -> None:
    """Bind every /api/shared/* route: config, pull, and the read mirrors."""
    register_shared_config_routes(app)
    register_shared_pull_routes(app)
    register_shared_mirror_routes(app)
