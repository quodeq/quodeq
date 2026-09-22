"""HTTP layer: the Flask app factory and every /api route module.

Re-exports ``create_app``; the route modules are registered through
``routes_registry.py`` rather than imported from here.
"""
from quodeq.api.app import create_app

__all__ = ["create_app"]
