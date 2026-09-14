"""Cluster 13 (R-FT-7) — _save_index's except narrowing.

``_save_index``'s atomic write previously caught bare ``Exception``. Narrowed
to ``OSError`` to match ``_load_index``'s already-narrowed read path
(``(OSError, json.JSONDecodeError)``) a few lines above it in the same file.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from quodeq.data.fs._index_cache import IndexCache
from quodeq.data.fs._index_io import _save_index


def test_save_index_oserror_is_caught_and_logged(tmp_path: Path, caplog):
    """A realistic write failure (target directory doesn't exist -> mkstemp
    raises OSError) is swallowed and logged, not raised."""
    missing_dir = tmp_path / "does-not-exist"
    cache = IndexCache()

    quodeq_logger = logging.getLogger("quodeq")
    quodeq_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING):
            _save_index(missing_dir, {"a.py": "hash1"}, cache=cache)
    finally:
        quodeq_logger.removeHandler(caplog.handler)

    assert "Could not save project index" in caplog.text


def test_save_index_type_error_propagates(tmp_path: Path):
    """R-FT-7 — a non-serializable index (a programming bug, not an I/O
    failure) must now propagate as TypeError instead of being silently
    swallowed by the old bare `except Exception`."""
    cache = IndexCache()
    # A set() is not JSON-serializable; json.dump raises TypeError, which is
    # outside the narrowed OSError-only catch.
    bad_index = {"a.py": {"not", "a", "string"}}

    with pytest.raises(TypeError):
        _save_index(tmp_path, bad_index, cache=cache)  # type: ignore[arg-type]
