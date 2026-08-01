"""Tests for the trend fetcher selection (scalar fast-path vs heavy rescoring)."""
from pathlib import Path

import pytest

from quodeq.core.types import DimensionResult
from quodeq.services._trend_fetcher import make_rescoring_fetcher
from quodeq.services.scoring import ScoringDeps, _make_trend_fetcher


def _make_project(tmp_path: Path) -> tuple[Path, str]:
    reports = tmp_path / "evaluations"
    (reports / "proj").mkdir(parents=True)
    return reports, "proj"


def test_no_dismissals_uses_scalar_reader(tmp_path: Path) -> None:
    reports, project = _make_project(tmp_path)  # fresh project -> no dismissals

    calls: list[str] = []

    def fake_scalar(rr, p, rid):
        calls.append(rid)
        return [DimensionResult(dimension="security", overall_score="8.0/10", overall_grade="Good")]

    deps = ScoringDeps(read_run_scalars=fake_scalar)
    fetcher = _make_trend_fetcher(reports, project, deps=deps)
    result = fetcher("r1")

    assert [d.overall_score for d in result] == ["8.0/10"]
    assert calls == ["r1"]  # scalar reader was used


def test_active_dismissal_uses_heavy_path(tmp_path: Path, monkeypatch) -> None:
    reports, project = _make_project(tmp_path)
    # Use a tmp score cache so the test stays isolated.
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))

    rescoring_calls: list[str] = []

    def fake_rescoring_fetcher(rr, p, params=None, *, base_fetcher=None, **_kw):
        def fetch(run_id: str) -> list[DimensionResult]:
            rescoring_calls.append(run_id)
            return [DimensionResult(dimension="security", overall_score="7.0/10", overall_grade="Fair")]
        return fetch

    # The heavy-path rescoring fetcher is built by the shared _trend_fetcher
    # factory (scoring._make_trend_fetcher delegates to it).
    monkeypatch.setattr("quodeq.services._trend_fetcher.make_rescoring_fetcher", fake_rescoring_fetcher)

    def boom(*_a):
        raise AssertionError("scalar reader used despite active dismissals")

    # A non-empty dismissed set forces the heavy path past the scalar reader.
    deps = ScoringDeps(
        read_run_scalars=boom,
        dismissed_keys=lambda _pd: {("R1", "a.py", 1)},
        deleted_keys=lambda _pd: set(),
    )
    fetcher = _make_trend_fetcher(reports, project, deps=deps)

    # Heavy path: the cache-wrapper is returned (not the raw rescoring fetcher).
    # Calling it must invoke the rescoring fetcher (not the scalar reader).
    result = fetcher("r1")
    assert [d.overall_score for d in result] == ["7.0/10"]
    assert rescoring_calls == ["r1"]  # rescoring fetcher was used, not the scalar reader


def test_active_deletion_uses_heavy_path(tmp_path: Path, monkeypatch) -> None:
    reports, project = _make_project(tmp_path)
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))

    rescoring_calls: list[str] = []

    def fake_rescoring_fetcher(rr, p, params=None, *, base_fetcher=None, **_kw):
        def fetch(run_id: str) -> list[DimensionResult]:
            rescoring_calls.append(run_id)
            return [DimensionResult(dimension="security", overall_score="6.0/10", overall_grade="Fair")]
        return fetch

    monkeypatch.setattr("quodeq.services._trend_fetcher.make_rescoring_fetcher", fake_rescoring_fetcher)

    def boom(*_a):
        raise AssertionError("scalar reader used despite active deletions")

    deps = ScoringDeps(
        read_run_scalars=boom,
        dismissed_keys=lambda _pd: set(),
        deleted_keys=lambda _pd: {("sec", "prin", "a.py")},
    )
    fetcher = _make_trend_fetcher(reports, project, deps=deps)

    # Heavy path: rescoring fetcher is wrapped in the cache; scalar reader must NOT be called.
    result = fetcher("r2")
    assert [d.overall_score for d in result] == ["6.0/10"]
    assert rescoring_calls == ["r2"]


def test_make_rescoring_fetcher_rejects_traversal_project(tmp_path: Path) -> None:
    """``make_rescoring_fetcher`` builds its own ``project_dir`` join
    independent of any caller-side validation, so a traversal project must be
    rejected locally before that join (CodeQL py/path-injection build site)."""
    with pytest.raises(ValueError):
        make_rescoring_fetcher(tmp_path, "../etc", base_fetcher=lambda run_id: [])
