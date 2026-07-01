"""Tests for the trend fetcher selection (scalar fast-path vs heavy rescoring)."""
from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.services.scoring import _make_trend_fetcher


def _make_project(tmp_path: Path) -> tuple[Path, str]:
    reports = tmp_path / "evaluations"
    (reports / "proj").mkdir(parents=True)
    return reports, "proj"


def test_no_dismissals_uses_scalar_reader(tmp_path: Path, monkeypatch) -> None:
    reports, project = _make_project(tmp_path)  # fresh project -> no dismissals

    calls: list[str] = []

    def fake_scalar(rr, p, rid):
        calls.append(rid)
        return [DimensionResult(dimension="security", overall_score="8.0/10", overall_grade="Good")]

    # _make_trend_fetcher passes the module-global read_run_scalars as the
    # reader (an explicit arg, so patching the module global takes effect).
    monkeypatch.setattr("quodeq.services.scoring.read_run_scalars", fake_scalar)

    fetcher = _make_trend_fetcher(reports, project)
    result = fetcher("r1")

    assert [d.overall_score for d in result] == ["8.0/10"]
    assert calls == ["r1"]  # scalar reader was used


def test_active_dismissal_uses_heavy_path(tmp_path: Path, monkeypatch) -> None:
    reports, project = _make_project(tmp_path)
    # Force a non-empty dismissed set so the scalar fast path is bypassed.
    monkeypatch.setattr("quodeq.services.scoring.dismissed_keys", lambda _pd: {("R1", "a.py", 1)})
    monkeypatch.setattr("quodeq.services.scoring.deleted_keys", lambda _pd: set())

    sentinel = object()
    monkeypatch.setattr("quodeq.services.scoring._make_rescoring_fetcher",
                        lambda rr, p, params=None: sentinel)

    def boom(*_a):
        raise AssertionError("scalar reader used despite active dismissals")
    monkeypatch.setattr("quodeq.services.scoring.read_run_scalars", boom)

    fetcher = _make_trend_fetcher(reports, project)

    # Heavy path: _make_trend_fetcher returns the rescoring fetcher unchanged.
    assert fetcher is sentinel
