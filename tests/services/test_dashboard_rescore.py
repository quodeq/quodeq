"""Tests for quodeq.services.dashboard — _rescore_run_dimensions path
validation.

Split from test_dashboard.py.
"""
from __future__ import annotations

import pytest

from quodeq.services.dashboard import _rescore_run_dimensions


class TestRescoreRunDimensionsValidatesPathSegments:
    """``_rescore_run_dimensions`` builds its own ``project_dir`` / ``run_dir``
    joins independent of any upstream validation, so a traversal project or
    run_id must be rejected locally before either join (CodeQL
    py/path-injection build site)."""

    def test_rejects_traversal_project(self, tmp_path):
        with pytest.raises(ValueError):
            _rescore_run_dimensions([], tmp_path, "../etc", "run1", params=None)

    def test_rejects_traversal_run_id(self, tmp_path, monkeypatch):
        # Force past the "no active suppressions" early return so the
        # run_id join at :196 is actually reached. dashboard.py imports
        # these two at module level (not deferred), so the patch target is
        # dashboard's own name binding, not the origin modules.
        monkeypatch.setattr(
            "quodeq.services.dashboard.dismissed_keys", lambda _pd: {("R1", "a.py", 1)})
        monkeypatch.setattr("quodeq.services.dashboard.deleted_keys", lambda _pd: set())
        with pytest.raises(ValueError):
            _rescore_run_dimensions([], tmp_path, "proj", "../../etc/passwd", params=None)
