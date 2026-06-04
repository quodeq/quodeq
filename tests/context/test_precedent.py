import json
from pathlib import Path

import pytest

from quodeq.context.precedent import fingerprint, load_precedent_fingerprints
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services.dismissed import dismiss_finding


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _seed_dismissed(
    project_dir: Path,
    run_id: str,
    *,
    req: str,
    snippet: str,
    file: str,
    line: int,
) -> Path:
    """Seed a violation into a run, dismiss it, then project into SQL."""
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file=file, line=line, reason="r", req=req, snippet=snippet,
    )))
    # Dismiss via the new service (writes to actions.jsonl).
    dismiss_finding(project_dir, {"req": req, "file": file, "line": line})
    # Project both events.jsonl and actions.jsonl into evaluation.db.
    Projector().ensure_projected(log, run_dir, project_dir=project_dir)
    return run_dir


# ---------------------------------------------------------------------------
# New SQL-based test (was the failing regression)
# ---------------------------------------------------------------------------


def test_load_reads_dismissed_from_sql(tmp_path: Path) -> None:
    """load_precedent_fingerprints must read from SQL, not dismissed.json."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _seed_dismissed(
        project_dir, "r1",
        req="S-CON-1", snippet="password = 'secret'",
        file="auth.py", line=42,
    )
    # No dismissed.json exists; the fingerprint must still be found via SQL.
    assert not (project_dir / "dismissed.json").exists()

    out = load_precedent_fingerprints(project_dir)

    assert fingerprint("S-CON-1", "password = 'secret'") in out


def test_load_aggregates_across_multiple_runs(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _seed_dismissed(project_dir, "r1", req="R1", snippet="x = 1", file="a.py", line=1)
    _seed_dismissed(project_dir, "r2", req="R2", snippet="y = 2", file="b.py", line=2)

    out = load_precedent_fingerprints(project_dir)

    assert fingerprint("R1", "x = 1") in out
    assert fingerprint("R2", "y = 2") in out


# ---------------------------------------------------------------------------
# Fingerprint unit tests (unchanged -- no DB involved)
# ---------------------------------------------------------------------------


def test_fingerprint_is_stable_for_same_inputs():
    a = fingerprint("S-CON-1", "password = 'secret'")
    b = fingerprint("S-CON-1", "password = 'secret'")
    assert a == b
    assert a is not None


def test_fingerprint_normalizes_whitespace():
    a = fingerprint("S-CON-1", "password = 'secret'")
    b = fingerprint("S-CON-1", "  password = 'secret'  ")
    c = fingerprint("S-CON-1", "password\t=\t'secret'")
    assert a == b == c


def test_fingerprint_changes_with_req():
    a = fingerprint("S-CON-1", "x = 1")
    b = fingerprint("S-CON-2", "x = 1")
    assert a != b


def test_fingerprint_changes_with_snippet():
    a = fingerprint("S-CON-1", "x = 1")
    b = fingerprint("S-CON-1", "y = 1")
    assert a != b


def test_fingerprint_returns_none_for_empty_inputs():
    assert fingerprint(None, None) is None
    assert fingerprint("", "") is None
    assert fingerprint("  ", "  ") is None


def test_fingerprint_works_with_only_req():
    assert fingerprint("S-CON-1", None) is not None
    assert fingerprint("S-CON-1", "") is not None


def test_fingerprint_strips_trailing_punctuation():
    a = fingerprint("R", "do_it()")
    b = fingerprint("R", "do_it();")
    c = fingerprint("R", "do_it().")
    assert a == b == c


def test_load_returns_empty_for_missing_dir(tmp_path: Path):
    assert load_precedent_fingerprints(tmp_path / "missing") == set()


def test_load_returns_empty_for_project_with_no_runs(tmp_path: Path):
    """Project dir with no run sub-directories returns an empty set."""
    assert load_precedent_fingerprints(tmp_path) == set()


def test_load_skips_subdirs_without_db(tmp_path: Path):
    """Subdirectories without an evaluation.db are silently skipped."""
    (tmp_path / "r_no_db").mkdir()
    assert load_precedent_fingerprints(tmp_path) == set()


def test_load_returns_fingerprints_from_sql(tmp_path: Path):
    """Dismissed findings stored in SQL are returned as fingerprints."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _seed_dismissed(project_dir, "r1", req="S-CON-1", snippet="password = 'secret'",
                    file="x.py", line=1)
    _seed_dismissed(project_dir, "r2", req="M-MOD-2", snippet="def foo(): pass",
                    file="y.py", line=5)

    out = load_precedent_fingerprints(project_dir)

    assert len(out) == 2
    assert fingerprint("S-CON-1", "password = 'secret'") in out
    assert fingerprint("M-MOD-2", "def foo(): pass") in out


def test_load_skips_run_dirs_without_db(tmp_path: Path):
    """A run directory with no evaluation.db is silently skipped."""
    project_dir = tmp_path / "proj"
    (project_dir / "r_no_db").mkdir(parents=True)
    # Only a real dismissed run seeds the expected fingerprint.
    _seed_dismissed(project_dir, "r_real", req="X", snippet="s", file="f.py", line=1)

    out = load_precedent_fingerprints(project_dir)

    assert fingerprint("X", "s") in out


def test_load_skips_findings_with_blank_req_and_snippet(tmp_path: Path):
    """Findings whose fingerprint resolves to None are not added to the set."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    # Seed a real finding to ensure the DB exists with *some* rows.
    _seed_dismissed(project_dir, "r1", req="REAL", snippet="code()", file="a.py", line=1)

    out = load_precedent_fingerprints(project_dir)

    # Only the real fingerprint is present.
    assert fingerprint("REAL", "code()") in out
    assert fingerprint("", "") not in out
