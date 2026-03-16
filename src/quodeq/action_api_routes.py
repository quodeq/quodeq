"""Re-export shim — moved to quodeq.api.routes."""
from quodeq.api.routes import (
    register_project_list_routes,
    register_project_data_routes,
    register_evaluation_list_routes,
    register_evaluation_item_routes,
    register_discovery_routes,
    register_static_routes,
)

__all__ = [
    "register_project_list_routes",
    "register_project_data_routes",
    "register_evaluation_list_routes",
    "register_evaluation_item_routes",
    "register_discovery_routes",
    "register_static_routes",
]
