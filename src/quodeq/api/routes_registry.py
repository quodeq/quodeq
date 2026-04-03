"""Central route registration for the Flask application."""

from __future__ import annotations

from flask import Flask

from quodeq.api._rate_limit import RateLimitStore
from quodeq.api.routes import (
    register_project_list_routes,
    register_project_data_routes,
    register_evaluation_list_routes,
    register_evaluation_item_routes,
    register_discovery_routes,
    register_static_routes,
)
from quodeq.api.standards_routes import register_standards_routes
from quodeq.api.routes_findings import register_findings_routes
from quodeq.api.routes_rescore import register_rescore_routes
from quodeq.services.base import ActionProvider


def register_all_routes(
    app: Flask, provider: ActionProvider,
    eval_store: RateLimitStore, static_dist: str | None,
) -> None:
    """Register all API route groups on the app.

    Args:
        app: The Flask application instance.
        provider: Action provider for evaluation and project operations.
        eval_store: Rate-limit store for evaluation requests.
        static_dist: Optional path to the static assets directory.
    """
    register_project_list_routes(app, provider)
    register_project_data_routes(app, provider)
    register_evaluation_list_routes(app, provider, eval_store)
    register_evaluation_item_routes(app, provider)
    register_discovery_routes(app, provider)
    register_standards_routes(app)
    register_findings_routes(app)
    register_rescore_routes(app)
    register_static_routes(app, static_dist)
