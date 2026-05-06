"""Regression: tests must never touch the developer's real ``~/.quodeq``.

A pytest run that constructs ``FilesystemActionProvider()`` with no explicit
``index_db_path`` previously fell through to ``Path.home() / ".quodeq" /
"index.db"`` and wrote test rows to the user's production DB — leaving stuck
"running" jobs that the dashboard then auto-resumed. The autouse fixture in
``tests/conftest.py`` must redirect ``QUODEQ_INDEX_DB_PATH`` and
``QUODEQ_EVALUATIONS_DIR`` at a per-test tmp dir so this can't happen.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.shared._env import get_evaluations_dir, get_index_db_path


def test_default_index_db_path_resolves_inside_tmp() -> None:
    real_home_db = str(Path.home() / ".quodeq" / "index.db")
    resolved = get_index_db_path()
    assert resolved != real_home_db, (
        f"get_index_db_path() returned the production path {resolved}; "
        "the autouse isolation fixture is not setting QUODEQ_INDEX_DB_PATH"
    )


def test_default_evaluations_dir_resolves_inside_tmp() -> None:
    real_home_dir = str(Path.home() / ".quodeq" / "evaluations")
    resolved = get_evaluations_dir()
    assert resolved != real_home_dir, (
        f"get_evaluations_dir() returned the production path {resolved}; "
        "the autouse isolation fixture is not setting QUODEQ_EVALUATIONS_DIR"
    )


def test_default_provider_open_index_writes_to_tmp() -> None:
    """The exact failure mode that polluted ~/.quodeq/index.db: provider
    constructed with no kwargs and ``_open_index`` lazily resolves the path."""
    provider = FilesystemActionProvider()
    db = provider._open_index()
    try:
        # The lazy resolver in _open_index sets _index_db_path to the resolved
        # value; assert it is not the real home DB.
        real_home_db = Path.home() / ".quodeq" / "index.db"
        assert provider._index_db_path != real_home_db, (
            f"FilesystemActionProvider() opened the production DB at "
            f"{provider._index_db_path}; isolation fixture is broken"
        )
    finally:
        db.close()
