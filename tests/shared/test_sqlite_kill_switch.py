import io
from pathlib import Path

import pytest

from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.shared._env import sqlite_disabled


def test_sqlite_disabled_default(monkeypatch):
    monkeypatch.delenv("QUODEQ_DISABLE_SQLITE", raising=False)
    assert sqlite_disabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_sqlite_disabled_respects_truthy_values(monkeypatch, value):
    monkeypatch.setenv("QUODEQ_DISABLE_SQLITE", value)
    assert sqlite_disabled() is True


@pytest.mark.parametrize("value", ["0", "false", "", "no"])
def test_sqlite_disabled_falsy_values(monkeypatch, value):
    monkeypatch.setenv("QUODEQ_DISABLE_SQLITE", value)
    assert sqlite_disabled() is False


def test_router_skips_sqlite_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_SQLITE", "1")
    fh = io.StringIO()
    repo = SqliteFindingsRepository(tmp_path)
    router = FindingsRouter(fh, findings_repo=repo)
    router.receive({"p": "P1", "file": "x.py", "line": 1, "t": "violation",
                    "severity": "medium", "d": "dim", "reason": "r",
                    "snippet": "s", "w": "t"})
    # JSONL written
    assert fh.getvalue().count("\n") == 1
    # SQLite untouched
    assert repo.count_by_dimension() == {}


def test_load_evidence_map_skips_sqlite_when_disabled(tmp_path: Path, monkeypatch):
    """When kill switch is set, the loader does NOT use SQLite even if evaluation.db exists."""
    monkeypatch.setenv("QUODEQ_DISABLE_SQLITE", "1")
    run_dir = tmp_path
    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding({"p": "P1", "file": "x.py", "line": 1, "t": "violation",
                         "severity": "medium", "d": "dim", "reason": "r",
                         "snippet": "s", "w": "t"})
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()
    # No JSON files; if SQLite is consulted we'd see "dim", but with kill switch we should not.
    from quodeq.data.fs.report_parser._evidence import load_evidence_map
    result = load_evidence_map(evidence_dir)
    assert result == {}
