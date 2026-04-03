"""Route registration hub — re-exports all route groups for backwards compatibility."""
from __future__ import annotations

from quodeq.api.helpers import register_static_routes  # noqa: F401
from quodeq.api.routes_common import reports_dir as _reports_dir  # noqa: F401  — used by routes_evaluation
from quodeq.api.routes_project_list import register_project_list_routes  # noqa: F401
from quodeq.api.routes_project_data import register_project_data_routes  # noqa: F401
from quodeq.api.routes_discovery import register_discovery_routes  # noqa: F401

# Re-export evaluation routes so existing imports from this module keep working.
from quodeq.api.routes_evaluation import (  # noqa: F401
    register_evaluation_list_routes,
    register_evaluation_item_routes,
)

__all__ = [
    "register_static_routes",
    "register_project_list_routes",
    "register_project_data_routes",
    "register_discovery_routes",
    "register_evaluation_list_routes",
    "register_evaluation_item_routes",
    "_reports_dir",
]
