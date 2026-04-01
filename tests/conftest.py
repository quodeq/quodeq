"""Shared test fixtures and helpers."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure tests always load the worktree's source, not the installed package.
_WORKTREE_SRC = str(Path(__file__).parent.parent / "src")
if _WORKTREE_SRC not in sys.path:
    sys.path.insert(0, _WORKTREE_SRC)

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
