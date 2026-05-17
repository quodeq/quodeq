"""Shared fixtures for tests/services/scoring/."""
from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _caplog_quodeq(caplog: pytest.LogCaptureFixture) -> None:
    """Attach pytest's log-capture handler to the quodeq logger.

    The quodeq logger has propagate=False (set in shared/logging.py), so records
    never reach the root logger where caplog normally installs its handler.
    Attaching caplog.handler directly to quodeq ensures caplog.records works in
    tests that use the quodeq.* logger hierarchy.
    """
    quodeq_logger = logging.getLogger("quodeq")
    quodeq_logger.addHandler(caplog.handler)
    yield
    quodeq_logger.removeHandler(caplog.handler)
