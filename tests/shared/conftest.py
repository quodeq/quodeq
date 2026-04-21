"""Shared fixtures for tests/shared package."""
from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=False)
def no_raise_logging_exceptions():
    """Temporarily disable logging.raiseExceptions for tests that verify
    handlers swallow errors silently.

    Python 3.14 + pytest raises logging format errors as test failures by
    default (pytest overrides logging.Handler.handleError to re-raise).
    Tests that assert *our* handler is silent need this fixture to prevent
    pytest's own LogCaptureHandler from interfering.
    """
    original = logging.raiseExceptions
    logging.raiseExceptions = False
    try:
        yield
    finally:
        logging.raiseExceptions = original
