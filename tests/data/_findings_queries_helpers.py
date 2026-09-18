"""Seeding helpers for tests/data/test_findings_queries*.py siblings."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _seed(run_dir: Path, **kw) -> None:
    defaults = dict(
        practice_id="P1", verdict="violation", dimension="clean-architecture",
        file="src/a.py", line=10, reason="r", req="X-1", severity="major",
        title="t", snippet="s",
    )
    SQLiteStateStore(run_dir).record_finding(Judgment(**{**defaults, **kw}))


def _break_reopen_with_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """After this, the next open_evaluation_db() call raises RuntimeError
    (wrapping sqlite3.OperationalError), mirroring a locked/IO-erroring DB.
    Mirrors the technique in tests/data/sqlite/test_connection.py."""
    monkeypatch.setattr(
        "quodeq.data.sqlite.connection.apply_evaluation_schema",
        lambda conn: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
    )
