"""Guards for precedent_fingerprint's documented graceful-degradation contract.

``load_precedent_fingerprints``'s own docstring says "Missing or locked DBs
are skipped -- precedent matching degrades gracefully and never breaks a
scan," but nothing wrapped the read call: an exception out of
``read_dismissed_snippets`` (e.g. sqlite3.OperationalError on a locked DB)
propagated straight out and failed the whole run.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quodeq.context.precedent_fingerprint import load_precedent_fingerprints


def test_locked_db_is_skipped_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)

    def _boom(run_dir: Path) -> list[tuple[str | None, str | None]]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        "quodeq.data.sqlite.findings_queries.read_dismissed_snippets", _boom,
    )

    result = load_precedent_fingerprints(project_dir)

    assert result == set()  # degrades gracefully, doesn't raise
