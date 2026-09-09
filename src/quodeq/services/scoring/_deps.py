"""Re-export shim: the leaf now lives at ``quodeq.services._scoring_deps``.

Moved out of the ``scoring`` package so modules outside it (``_dashboard_history.py``,
``_trend_fetcher.py``) can import ``ScoringDeps`` without triggering
``scoring/__init__.py`` (which imports ``services/dashboard.py``, which
imports back into ``_dashboard_history.py`` — a same-layer cycle). Kept here
as a thin re-export so the in-package importers keep resolving unchanged.
"""
from __future__ import annotations

from quodeq.services._scoring_deps import ScoringDeps, _NO_DEPS  # noqa: F401
