"""Central route registration for the Flask application."""

from __future__ import annotations

from flask import Flask

from quodeq.api._log_buffer import LogBuffer
from quodeq.api._index_routes import register_index_routes
from quodeq.api._log_routes import register_log_routes
from quodeq.api._log_stream_routes import register_log_stream_routes
from quodeq.api._run_events_routes import register_run_events_routes
from quodeq.api._ollama_log_routes import register_ollama_log_routes
from quodeq.api._llamacpp_log_routes import register_llamacpp_log_routes
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
from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.api.terminal_routes import register_terminal_routes
from quodeq.api.routes_findings import register_findings_routes
from quodeq.api.llm_bridge_routes import register_llm_bridge_routes
from quodeq.api.routes_rescore import register_rescore_routes
from quodeq.api.routes_update import register_update_routes
from quodeq.api._scores_routes import register_scores_routes
from quodeq.api._grade_formula_routes import register_grade_formula_routes
from quodeq.services.base import ActionProvider


def register_all_routes(
    app: Flask, provider: ActionProvider,
    eval_store: RateLimitStore, static_dist: str | None,
    log_buffer: LogBuffer | None = None,
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
    register_log_stream_routes(app)
    register_run_events_routes(app)
    register_ollama_log_routes(app)
    register_llamacpp_log_routes(app)
    register_discovery_routes(app, provider)
    register_standards_routes(app)
    register_assistant_routes(app)
    register_terminal_routes(app)
    register_findings_routes(app)
    register_rescore_routes(app)
    register_scores_routes(app)
    register_grade_formula_routes(app)
    register_llm_bridge_routes(app)
    if log_buffer:
        register_log_routes(app, log_buffer)
    register_update_routes(app)
    register_index_routes(app)
    register_static_routes(app, static_dist)
