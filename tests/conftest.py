"""Shared test fixtures and helpers."""
from __future__ import annotations

import pytest


class DummyProcess:
    """Minimal process stub for tests that need a mock subprocess."""

    def __init__(self):
        self._returncode = 0

    def wait(self):
        return self._returncode

    def poll(self):
        return self._returncode

    def terminate(self):
        pass


@pytest.fixture
def dummy_process():
    """Return a DummyProcess instance."""
    return DummyProcess()
