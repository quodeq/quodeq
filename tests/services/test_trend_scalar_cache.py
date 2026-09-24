"""The trend fetcher's scalar fast path caches reads across requests.

Every /scores and /dashboard request walks the whole history window through
the trend fetcher. With a per-call cache that meant re-reading every run from
disk on every request. The cache now lives for the process, so each test
checks one way an entry must still be invalidated.
"""
import json
from pathlib import Path

from quodeq.core.types import DimensionResult, Finding
from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.scoring import ScoringDeps, make_scoring_trend_fetcher


def _project(tmp_path: Path) -> tuple[Path, str]:
    reports = tmp_path / "evaluations"
    (reports / "proj" / "r1").mkdir(parents=True)
    return reports, "proj"


def _counting_reader(calls: list[str], score: str = "8.0/10"):
    def read(_rr, _p, run_id):
        calls.append(run_id)
        return [DimensionResult(dimension="security", overall_score=score, overall_grade="Good")]
    return read


def _fetch(reports: Path, project: str, reader, run_id: str = "r1") -> list[DimensionResult]:
    return make_scoring_trend_fetcher(reports, project, deps=ScoringDeps(read_run_scalars=reader))(run_id)


def test_second_request_reuses_the_first_read(tmp_path: Path) -> None:
    reports, project = _project(tmp_path)
    calls: list[str] = []
    reader = _counting_reader(calls)

    _fetch(reports, project, reader)
    result = _fetch(reports, project, reader)

    assert [d.overall_score for d in result] == ["8.0/10"]
    assert calls == ["r1"]


def test_new_run_events_invalidate_the_entry(tmp_path: Path) -> None:
    reports, project = _project(tmp_path)
    events = reports / project / "r1" / "events.jsonl"
    events.write_text('{"e": 1}\n')
    calls: list[str] = []
    reader = _counting_reader(calls)

    _fetch(reports, project, reader)
    with events.open("a") as fh:
        fh.write('{"e": 2}\n')
    _fetch(reports, project, reader)

    assert calls == ["r1", "r1"]


def test_new_project_actions_invalidate_the_entry(tmp_path: Path) -> None:
    reports, project = _project(tmp_path)
    actions = reports / project / "actions.jsonl"
    calls: list[str] = []
    reader = _counting_reader(calls)

    _fetch(reports, project, reader)
    actions.write_text('{"action": "verify"}\n')
    _fetch(reports, project, reader)

    assert calls == ["r1", "r1"]


def test_grade_algo_bump_invalidates_the_entry(tmp_path: Path, monkeypatch) -> None:
    reports, project = _project(tmp_path)
    calls: list[str] = []
    reader = _counting_reader(calls)

    _fetch(reports, project, reader)
    monkeypatch.setattr("quodeq.core.scoring.projector_scoring.GRADE_ALGO_VERSION", 999)
    _fetch(reports, project, reader)

    assert calls == ["r1", "r1"]


def test_formula_change_hook_clears_the_cache(tmp_path: Path) -> None:
    reports, project = _project(tmp_path)
    calls: list[str] = []
    reader = _counting_reader(calls)

    _fetch(reports, project, reader)
    clear_shared_dimension_cache()
    _fetch(reports, project, reader)

    assert calls == ["r1", "r1"]


def test_in_progress_run_is_read_fresh(tmp_path: Path) -> None:
    reports, project = _project(tmp_path)
    (reports / project / "r1" / "status.json").write_text(json.dumps({"state": "running"}))
    calls: list[str] = []
    reader = _counting_reader(calls)

    _fetch(reports, project, reader)
    _fetch(reports, project, reader)

    assert calls == ["r1", "r1"]


def test_cached_entry_drops_findings(tmp_path: Path) -> None:
    """A run without SQL grade tables falls back to the full reader, which
    returns findings. The trend only needs scalars, so the process-wide
    cache must not pin multi-MB finding lists for every such run."""
    reports, project = _project(tmp_path)
    finding = Finding(file="a.py", line=1, title="x")

    def full_reader(_rr, _p, _run_id):
        return [DimensionResult(
            dimension="security", overall_score="7.0/10", overall_grade="Fair",
            violations=[finding], compliance=[finding],
        )]

    result = _fetch(reports, project, full_reader)

    assert [d.overall_score for d in result] == ["7.0/10"]
    assert result[0].violations == [] and result[0].compliance == []


def test_run_outside_cacheable_set_is_read_fresh(tmp_path: Path) -> None:
    """Callers pass the DONE runs as ``cacheable_run_ids``. A run they know is
    still going must be re-read even when its status.json is missing."""
    reports, project = _project(tmp_path)
    calls: list[str] = []
    deps = ScoringDeps(read_run_scalars=_counting_reader(calls))

    for _ in range(2):
        make_scoring_trend_fetcher(reports, project, cacheable_run_ids={"other"}, deps=deps)("r1")

    assert calls == ["r1", "r1"]
