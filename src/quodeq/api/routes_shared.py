"""Routes for the shared results repository (config, status, refresh, publish),
plus read-only mirrors of the project read endpoints scoped to the shared clone.

Read-only invariant: no finding-mutation routes exist in this module or
anywhere under /api/shared/*. Every ``/api/shared/projects/...`` route is a
thin GET-only delegation to the same service functions the local
``/api/projects/...`` routes use, pointed at the shared clone's evaluations
root (via ``_with_shared_root``) instead of the local reports directory.

Split (Task 9) into four modules plus this thin orchestrator:
  - routes_shared_common.py: ``_with_shared_root``, ``_validate_segment``,
    ``_shared_project_dir``, shared by the three registrars below.
  - routes_shared_config.py: status / config PUT-DELETE / refresh / publish.
  - routes_shared_pull.py: the one write exception to the read-only
    invariant (materializing a shared project as a local copy).
  - routes_shared_mirrors.py: the read-only mirrors of the project routes.

``refresh_shared_clone``, ``sync_shared_index``, and ``start_publish`` stay
imported here (unused directly) so tests can keep patching
"quodeq.api.routes_shared.<name>" — the split registrars look them up on
this module at call time rather than binding their own copies.
"""
from __future__ import annotations

from flask import Flask

from quodeq.services.shared_publish import start_publish  # noqa: F401 — re-export/patch target
from quodeq.services.shared_repo import (  # noqa: F401 — re-export/patch target
    refresh_shared_clone,
    sync_shared_index,
)

from .routes_shared_common import (  # noqa: F401 — re-export
    _logger,
    _shared_project_dir,
    _validate_segment,
    _with_shared_root,
)
from .routes_shared_config import register_shared_config_routes
from .routes_shared_pull import register_shared_pull_routes
from .routes_shared_mirrors import register_shared_mirror_routes


def register_shared_routes(app: Flask) -> None:
    register_shared_config_routes(app)
    register_shared_pull_routes(app)
    register_shared_mirror_routes(app)
