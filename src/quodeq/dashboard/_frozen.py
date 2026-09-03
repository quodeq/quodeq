"""Frozen-app subprocess helpers — re-exported from quodeq.shared.frozen.

The implementation moved to shared/ (cross-cutting, stdlib-only) when the
built-in menu bar needed the same launch vocabulary without importing the
dashboard layer. This module keeps the dashboard-side import path stable.
"""
from quodeq.shared.frozen import (  # noqa: F401 — re-export
    dashboard_cmd,
    is_frozen,
    source_user_path,
    subprocess_cmd,
)
