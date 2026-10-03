"""Evaluation listing, creation, status, and cancellation route registrations.

Thin facade: the endpoints live in routes_evaluations_list.py and
routes_evaluations_item.py, and the shared already-scored claims owner
(``ScoringClaims``, one per app) lives in services/scored_jobs_registry.py.
Kept here so existing imports/patches (``quodeq.api._evaluation_routes.<name>``)
continue to resolve.

``score_completed_evidence`` is re-exported only because
tests/services/test_cancel_discard_purge_scoring.py still patches it by this
name; the production call (services/score_run.score_terminal_run_once) now
calls the module-local ``score_completed_evidence`` directly, so this copy
is not on that call path.
"""
from __future__ import annotations

from quodeq.services.score_run import score_completed_evidence  # noqa: F401 — legacy patch target, see docstring

from quodeq.api.routes_evaluations_list import register_evaluation_list_routes  # noqa: F401
from quodeq.api.routes_evaluations_item import register_evaluation_item_routes  # noqa: F401
