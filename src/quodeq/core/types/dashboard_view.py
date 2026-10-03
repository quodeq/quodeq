"""Which shape of the dashboard payload a client asked for.

``full`` carries every dimension's violation and compliance bodies (the
run-detail views need them); ``overview`` leaves those keys out, since the
Overview renders only scalars, the trend and the since-baseline block. The
UI mirror is ``ui/src/vocab/dashboardView.js``.
"""
from __future__ import annotations

from enum import StrEnum


class DashboardView(StrEnum):
    """The two dashboard payload shapes; the wire value of ``?view=``."""

    FULL = "full"
    OVERVIEW = "overview"
