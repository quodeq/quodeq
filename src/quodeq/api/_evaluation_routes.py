"""Evaluation listing, creation, status, and cancellation route registrations.

Thin facade: the endpoints live in routes_evaluations_list.py and
routes_evaluations_item.py, and the shared already-scored registry lives in
_scored_jobs_registry.py. Kept here so existing imports/patches
(``quodeq.api._evaluation_routes.<name>``) continue to resolve.
"""
from __future__ import annotations

from quodeq.services.score_run import score_completed_evidence  # noqa: F401 — re-export/patch target

from quodeq.api._scored_jobs_registry import (  # noqa: F401
    _scored_jobs,
    _scored_jobs_lock,
    _SCORED_JOBS_MAX,
    _claim_scoring,
    _release_scoring,
    reset_scored_jobs,
)
from quodeq.api.routes_evaluations_list import register_evaluation_list_routes  # noqa: F401
from quodeq.api.routes_evaluations_item import register_evaluation_item_routes  # noqa: F401
