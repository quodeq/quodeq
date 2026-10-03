"""Tests for the trend fetcher: untouched runs read their scalars, touched runs rescore."""
from pathlib import Path

import pytest

from quodeq.core.types import DimensionResult
from quodeq.services.trend_fetcher import make_rescoring_fetcher, make_trend_fetcher
from quodeq.services.scoring import ScoringDeps, make_scoring_trend_fetcher


def _make_project(tmp_path: Path, runs: tuple[str, ...] = ("r1",)) -> tuple[Path, str]:
    """A project whose *runs* each hold one security report (the scalar guard's disk set)."""
    reports = tmp_path / "evaluations"
    for run_id in runs:
        evaluation = reports / "proj" / run_id / "evaluation"
        evaluation.mkdir(parents=True)
        (evaluation / "security.json").write_text("{}")
    return reports, "proj"


def test_no_dismissals_uses_scalar_reader(tmp_path: Path) -> None:
    reports, project = _make_project(tmp_path)  # fresh project -> no dismissals

    calls: list[str] = []

    def fake_scalar(rr, p, rid, **_kw):
        calls.append(rid)
        return [DimensionResult(dimension="security", overall_score="8.0/10", overall_grade="Good")]

    deps = ScoringDeps(read_run_scalars=fake_scalar)
    fetcher = make_scoring_trend_fetcher(reports, project, deps=deps)
    result = fetcher("r1")

    assert [d.overall_score for d in result] == ["8.0/10"]
    assert calls == ["r1"]  # scalar reader was used


def _run_holds(monkeypatch, dismiss_keys: set, class_keys: set) -> None:
    """Make every run's key sets (the findings a suppression can touch) these."""
    monkeypatch.setattr("quodeq.services.run_keys.read_run_key_sets",
                        lambda _run_dir: (set(dismiss_keys), set(class_keys)))


def test_active_dismissal_uses_heavy_path(tmp_path: Path, monkeypatch) -> None:
    reports, project = _make_project(tmp_path)
    # Use a tmp score cache so the test stays isolated.
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _run_holds(monkeypatch, {("R1", "a.py", 1)}, set())

    rescoring_calls: list[str] = []

    def fake_rescoring_fetcher(rr, p, params=None, *, base_fetcher=None, **_kw):
        def fetch(run_id: str) -> list[DimensionResult]:
            rescoring_calls.append(run_id)
            return [DimensionResult(dimension="security", overall_score="7.0/10", overall_grade="Fair")]
        return fetch

    # The heavy-path rescoring fetcher is built by the shared trend_fetcher
    # factory (scoring.make_scoring_trend_fetcher delegates to it).
    monkeypatch.setattr("quodeq.services.trend_fetcher.make_rescoring_fetcher", fake_rescoring_fetcher)

    def boom(*_a):
        raise AssertionError("scalar reader used despite active dismissals")

    # A non-empty dismissed set forces the heavy path past the scalar reader.
    deps = ScoringDeps(
        read_run_scalars=boom,
        dismissed_keys=lambda _pd: {("R1", "a.py", 1)},
        deleted_keys=lambda _pd: set(),
    )
    fetcher = make_scoring_trend_fetcher(reports, project, deps=deps)

    # Heavy path: the cache-wrapper is returned (not the raw rescoring fetcher).
    # Calling it must invoke the rescoring fetcher (not the scalar reader).
    result = fetcher("r1")
    assert [d.overall_score for d in result] == ["7.0/10"]
    assert rescoring_calls == ["r1"]  # rescoring fetcher was used, not the scalar reader


def test_active_deletion_uses_heavy_path(tmp_path: Path, monkeypatch) -> None:
    reports, project = _make_project(tmp_path)
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _run_holds(monkeypatch, set(), {("sec", "prin", "a.py")})

    rescoring_calls: list[str] = []

    def fake_rescoring_fetcher(rr, p, params=None, *, base_fetcher=None, **_kw):
        def fetch(run_id: str) -> list[DimensionResult]:
            rescoring_calls.append(run_id)
            return [DimensionResult(dimension="security", overall_score="6.0/10", overall_grade="Fair")]
        return fetch

    monkeypatch.setattr("quodeq.services.trend_fetcher.make_rescoring_fetcher", fake_rescoring_fetcher)

    def boom(*_a):
        raise AssertionError("scalar reader used despite active deletions")

    deps = ScoringDeps(
        read_run_scalars=boom,
        dismissed_keys=lambda _pd: set(),
        deleted_keys=lambda _pd: {("sec", "prin", "a.py")},
    )
    fetcher = make_scoring_trend_fetcher(reports, project, deps=deps)

    # Heavy path: rescoring fetcher is wrapped in the cache; scalar reader must NOT be called.
    result = fetcher("r2")
    assert [d.overall_score for d in result] == ["6.0/10"]
    assert rescoring_calls == ["r2"]


def test_a_run_no_suppression_touches_reads_its_scalars(tmp_path: Path, monkeypatch) -> None:
    """With dismissals active elsewhere, an untouched run is not read in full."""
    reports, project = _make_project(tmp_path)
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _run_holds(monkeypatch, {("R9", "other.py", 7)}, {("sec", "prin", "other.py")})

    def fake_rescoring_fetcher(rr, p, params=None, *, base_fetcher=None, **_kw):
        def fetch(run_id: str) -> list[DimensionResult]:
            raise AssertionError("an untouched run was read in full and rescored")
        return fetch

    monkeypatch.setattr("quodeq.services.trend_fetcher.make_rescoring_fetcher", fake_rescoring_fetcher)
    scalar_calls: list[str] = []

    def fake_scalar(rr, p, rid, **_kw):
        scalar_calls.append(rid)
        return [DimensionResult(dimension="security", overall_score="8.0/10", overall_grade="Good")]

    deps = ScoringDeps(
        read_run_scalars=fake_scalar,
        dismissed_keys=lambda _pd: {("R1", "a.py", 1)},
        deleted_keys=lambda _pd: {("sec", "prin", "a.py")},
    )
    result = make_scoring_trend_fetcher(reports, project, deps=deps)("r1")

    assert [d.overall_score for d in result] == ["8.0/10"]
    assert scalar_calls == ["r1"]


def test_make_trend_fetcher_requires_a_base_fetcher_factory(tmp_path: Path) -> None:
    """``base_fetcher_factory`` has no leaf-level default, so omitting it fails
    up front instead of at the first cache miss."""
    reports, project = _make_project(tmp_path)

    with pytest.raises(TypeError):
        make_trend_fetcher(reports, project, deps=ScoringDeps(dismissed_keys=lambda _pd: set()))


def test_a_scalar_set_that_disagrees_with_the_reports_reads_the_run_in_full(
    tmp_path: Path, monkeypatch,
) -> None:
    """The grade tables answer for a run only when they cover every report on disk."""
    reports, project = _make_project(tmp_path)
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    full = [DimensionResult(dimension="security", overall_score="5.0/10", overall_grade="Fair")]
    deps = ScoringDeps(
        read_run_scalars=lambda rr, p, rid, **_kw: [],
        base_fetcher_factory=lambda rr, p: (lambda _rid: full),
        dismissed_keys=lambda _pd: set(), deleted_keys=lambda _pd: set(),
    )
    monkeypatch.setattr(
        "quodeq.services._accumulated_data._read_run_data_safely",
        lambda rr, p, rid, **_kw: full,
    )
    result = make_scoring_trend_fetcher(reports, project, deps=deps)("r1")
    assert [d.overall_score for d in result] == ["5.0/10"]


def test_make_rescoring_fetcher_rejects_traversal_project(tmp_path: Path) -> None:
    """``make_rescoring_fetcher`` builds its own ``project_dir`` join
    independent of any caller-side validation, so a traversal project must be
    rejected locally before that join (CodeQL py/path-injection build site)."""
    with pytest.raises(ValueError):
        make_rescoring_fetcher(tmp_path, "../etc", base_fetcher=lambda run_id: [])


def test_make_rescoring_fetcher_rejects_traversal_run_id(tmp_path: Path, monkeypatch) -> None:
    """The per-run ``run_dir`` join is reached only when a suppression is active;
    a traversal run_id must be rejected before it."""
    deps = ScoringDeps(dismissed_keys=lambda _pd: {("R1", "a.py", 1)}, deleted_keys=lambda _pd: set())
    fetch = make_rescoring_fetcher(tmp_path, "proj", base_fetcher=lambda run_id: [], deps=deps)
    with pytest.raises(ValueError):
        fetch("../../etc/passwd")


def test_fetching_one_run_does_not_decode_the_projects_whole_key_table(
    tmp_path: Path, monkeypatch,
) -> None:
    """A non-terminal run is never persisted, so its fetch used to decode every
    other run's key blobs for nothing (1 s per request on a 234-run project)."""
    reports, project = _make_project(tmp_path, runs=("r1", "r2"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    _run_holds(monkeypatch, {("R1", "a.py", 1)}, set())

    def fake_rescoring_fetcher(rr, p, params=None, *, base_fetcher=None, **_kw):
        def fetch(run_id: str) -> list[DimensionResult]:
            return [DimensionResult(dimension="security", overall_score="7.0/10", overall_grade="Fair")]
        return fetch

    monkeypatch.setattr("quodeq.services.trend_fetcher.make_rescoring_fetcher", fake_rescoring_fetcher)

    import quodeq.services.score_cache as sc
    looked_up: list[tuple[str, str]] = []
    real = sc.load_run_key_sets

    def one_row(conn, p, rid):
        looked_up.append((p, rid))
        return real(conn, p, rid)

    monkeypatch.setattr(sc, "load_run_key_sets", one_row)
    deps = ScoringDeps(
        dismissed_keys=lambda _pd: {("R1", "a.py", 1)},
        deleted_keys=lambda _pd: set(),
    )
    fetcher = make_scoring_trend_fetcher(reports, project, cacheable_run_ids={"r1"}, deps=deps)
    assert [d.overall_score for d in fetcher("r2")] == ["7.0/10"]
    assert [d.overall_score for d in fetcher("r1")] == ["7.0/10"]
    assert set(looked_up) == {("proj", "r2"), ("proj", "r1")}  # only the runs asked for
