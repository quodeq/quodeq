"""apply_to_all_runs progress / should_abort hooks (perf cycle 3, PR 1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.services import grade_formula

from tests.services._grade_formula_fixtures import formula_path  # noqa: F401 -- pytest fixture


def _make_runs(root: Path, names: list[str]) -> None:
    for name in names:
        run_dir = root / "proj" / name
        run_dir.mkdir(parents=True)
        (run_dir / "events.jsonl").write_text("")


def _started(root: Path, project: str, run: str, started_at: str) -> None:
    import json

    (root / project / run / "status.json").write_text(
        json.dumps({"started_at": started_at}), encoding="utf-8")


def _stub_recompute(monkeypatch, seen: list[str]) -> None:
    # grade_formula binds recompute_grades at import time (via wiring), so the
    # stub must target that binding, not quodeq.data.projection.grade_projector.
    monkeypatch.setattr(
        "quodeq.services.grade_formula.recompute_grades",
        lambda run_dir, params=None: seen.append(run_dir.name),
    )


def _count_cache_clears(monkeypatch) -> list[int]:
    cleared: list[int] = []
    monkeypatch.setattr(
        "quodeq.services.dashboard.clear_shared_dimension_cache",
        lambda: cleared.append(1),
    )
    return cleared


def test_progress_reports_the_total_first_then_each_run(tmp_path, formula_path, monkeypatch):
    _make_runs(tmp_path, ["r1", "r2", "r3"])
    _stub_recompute(monkeypatch, [])
    calls: list[tuple[int, int]] = []

    result = grade_formula.apply_to_all_runs(tmp_path, progress=lambda d, t: calls.append((d, t)))

    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert (result.rescored, result.failed, result.aborted) == (3, [], False)


def test_should_abort_stops_between_runs_and_still_clears_the_cache(tmp_path, formula_path, monkeypatch):
    _make_runs(tmp_path, ["r1", "r2", "r3"])
    seen: list[str] = []
    _stub_recompute(monkeypatch, seen)
    cleared = _count_cache_clears(monkeypatch)

    result = grade_formula.apply_to_all_runs(tmp_path, should_abort=lambda: len(seen) >= 1)

    assert len(seen) == 1  # the pass stops after the first run, whichever is newest
    assert (result.rescored, result.aborted) == (1, True)
    assert cleared == [1]


def test_cache_is_cleared_when_listing_the_runs_raises(tmp_path, formula_path, monkeypatch):
    cleared = _count_cache_clears(monkeypatch)

    def _boom(_root):
        raise OSError("reports dir vanished")

    monkeypatch.setattr(grade_formula, "_iter_event_log_runs", _boom)

    with pytest.raises(OSError):
        grade_formula.apply_to_all_runs(tmp_path)
    assert cleared == [1]


def test_missing_root_reports_a_zero_total(tmp_path, formula_path, monkeypatch):
    _count_cache_clears(monkeypatch)
    calls: list[tuple[int, int]] = []

    result = grade_formula.apply_to_all_runs(tmp_path / "nope", progress=lambda d, t: calls.append((d, t)))

    assert calls == [(0, 0)]
    assert result == grade_formula.ApplyResult(rescored=0, failed=[])


def test_the_pass_rewrites_the_newest_runs_of_the_most_recent_projects_first(tmp_path, formula_path, monkeypatch):
    """What people look at is every project's latest run; the pass starts
    there, most recently active project first, and the history follows."""
    for project, run in (("old-proj", "r1"), ("old-proj", "r2"), ("new-proj", "r1"), ("new-proj", "r2")):
        run_dir = tmp_path / project / run
        run_dir.mkdir(parents=True)
        (run_dir / "events.jsonl").write_text("")
    _started(tmp_path, "old-proj", "r1", "2026-01-01T00:00:00")
    _started(tmp_path, "old-proj", "r2", "2026-02-01T00:00:00")
    _started(tmp_path, "new-proj", "r1", "2026-03-01T00:00:00")
    _started(tmp_path, "new-proj", "r2", "2026-04-01T00:00:00")
    seen: list[str] = []
    monkeypatch.setattr(
        "quodeq.services.grade_formula.recompute_grades",
        lambda run_dir, params=None: seen.append(f"{run_dir.parent.name}/{run_dir.name}"),
    )
    calls: list[tuple[int, int]] = []

    result = grade_formula.apply_to_all_runs(tmp_path, progress=lambda d, t: calls.append((d, t)))

    assert seen == ["new-proj/r2", "new-proj/r1", "old-proj/r2", "old-proj/r1"]
    assert calls[0] == (0, 4)
    assert result.rescored == 4

