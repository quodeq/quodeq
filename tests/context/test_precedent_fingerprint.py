"""Guards for precedent_fingerprint's graceful-degradation contract and memo.

``load_precedent_fingerprints``'s own docstring says "Missing or locked DBs
are skipped -- precedent matching degrades gracefully and never breaks a
scan," but nothing wrapped the read call: an exception out of
``read_dismissed_snippets`` (e.g. sqlite3.OperationalError on a locked DB)
propagated straight out and failed the whole run.

The memo tests cover the second cost: every scan used to open and query
every run's database again even when nothing had changed since the last
scan. Reads are keyed on the injected source stamp and skipped while it
holds.
"""
from __future__ import annotations

import sqlite3
from collections import OrderedDict
from pathlib import Path

import pytest

from quodeq.context import precedent_fingerprint as pf
from quodeq.context.precedent_fingerprint import fingerprint, load_precedent_fingerprints


def _run(project_dir: Path, name: str) -> Path:
    run_dir = project_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


class _Reader:
    """Fake reader that records which run dirs were read, in order."""

    def __init__(self, rows: dict[str, list[tuple[str, str]]]) -> None:
        self.rows = rows
        self.calls: list[str] = []

    def __call__(self, run_dir: Path) -> list[tuple[str, str]]:
        self.calls.append(run_dir.name)
        return self.rows.get(run_dir.name, [])


def test_locked_db_is_skipped_not_raised(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _run(project_dir, "r1")

    def _boom(run_dir: Path) -> list[tuple[str | None, str | None]]:
        raise sqlite3.OperationalError("database is locked")

    result = load_precedent_fingerprints(
        project_dir, read_dismissed=_boom, source_stamp=lambda d: 1, cache=OrderedDict(),
    )

    assert result == set()  # degrades gracefully, doesn't raise


def test_unchanged_stamp_serves_later_scans_from_the_memo(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _run(project_dir, "r1")
    reader = _Reader({"r1": [("R1", "x = 1")]})
    cache: pf.PrecedentMemo = OrderedDict()

    first = load_precedent_fingerprints(
        project_dir, read_dismissed=reader, source_stamp=lambda d: (10, 1), cache=cache,
    )
    second = load_precedent_fingerprints(
        project_dir, read_dismissed=reader, source_stamp=lambda d: (10, 1), cache=cache,
    )

    assert first == second == {fingerprint("R1", "x = 1")}
    assert reader.calls == ["r1"]  # read once, then served from the memo


def test_changed_stamp_rereads_the_run(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _run(project_dir, "r1")
    reader = _Reader({"r1": [("R1", "x = 1")]})
    cache: pf.PrecedentMemo = OrderedDict()

    load_precedent_fingerprints(
        project_dir, read_dismissed=reader, source_stamp=lambda d: (10, 1), cache=cache,
    )
    reader.rows["r1"].append(("R2", "y = 2"))
    out = load_precedent_fingerprints(
        project_dir, read_dismissed=reader, source_stamp=lambda d: (12, 2), cache=cache,
    )

    assert reader.calls == ["r1", "r1"]
    assert out == {fingerprint("R1", "x = 1"), fingerprint("R2", "y = 2")}


def test_run_without_source_never_reaches_the_reader(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _run(project_dir, "no_db")
    _run(project_dir, "with_db")
    reader = _Reader({"with_db": [("R1", "x = 1")]})

    out = load_precedent_fingerprints(
        project_dir, read_dismissed=reader,
        source_stamp=lambda d: None if d.name == "no_db" else 1, cache=OrderedDict(),
    )

    assert reader.calls == ["with_db"]
    assert out == {fingerprint("R1", "x = 1")}


def test_failed_read_is_retried_on_the_next_scan(tmp_path: Path) -> None:
    """A locked DB must not be remembered as having no precedents."""
    project_dir = tmp_path / "project"
    _run(project_dir, "r1")
    attempts: list[int] = []

    def flaky(run_dir: Path) -> list[tuple[str, str]]:
        attempts.append(1)
        if len(attempts) == 1:
            raise sqlite3.OperationalError("database is locked")
        return [("R1", "x = 1")]

    cache: pf.PrecedentMemo = OrderedDict()
    first = load_precedent_fingerprints(
        project_dir, read_dismissed=flaky, source_stamp=lambda d: 1, cache=cache,
    )
    second = load_precedent_fingerprints(
        project_dir, read_dismissed=flaky, source_stamp=lambda d: 1, cache=cache,
    )

    assert first == set()
    assert second == {fingerprint("R1", "x = 1")}


def test_memo_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "_MEMO_MAX_RUNS", 2)
    project_dir = tmp_path / "project"
    for name in ("r1", "r2", "r3"):
        _run(project_dir, name)
    cache: pf.PrecedentMemo = OrderedDict()

    load_precedent_fingerprints(
        project_dir, read_dismissed=_Reader({}), source_stamp=lambda d: 1, cache=cache,
    )

    assert len(cache) == 2
