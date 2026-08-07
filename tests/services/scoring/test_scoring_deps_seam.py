"""ScoringDeps: injectable dependency bundle for the scoring reader.

The scoring module's tests patched its namespace attributes (read_run_data,
dismissed_keys, ...), which welded every caller to the module layout and
made the previous decomposition attempt revert. Public entry points now
accept a ``deps`` bundle; a None field resolves to the production callable
at call time, so the seam is purely additive.
"""
from __future__ import annotations

from dataclasses import replace

from quodeq.core.types.dimension import DimensionResult
from quodeq.core.types.finding import Finding


def _dim(name: str = "security") -> DimensionResult:
    return DimensionResult(
        dimension=name, overall_score="7.0/10", overall_grade="Good",
        principles=[], violations=[
            Finding(req="R1", file="a.py", line=1, severity="major"),
        ], compliance=[], totals=None,
    )


def test_scored_run_dimensions_uses_injected_deps(tmp_path):
    from quodeq.services.scoring import ScoringDeps, scored_run_dimensions

    (tmp_path / "proj" / "run-1").mkdir(parents=True)
    raw = _dim()
    rescored = replace(raw, overall_score="9.0/10")
    calls = {}

    def fake_rescore(d, dismissed, deleted, *, params, run_dir, rules=()):
        calls["args"] = (d, dismissed, deleted, run_dir)
        return rescored

    deps = ScoringDeps(
        read_run_data=lambda root, p, r: [raw],
        dismissed_keys=lambda pd: {("R1", "a.py", 1)},
        deleted_keys=lambda pd: set(),
        rescore_dimension=fake_rescore,
    )
    out = scored_run_dimensions(tmp_path, "proj", "run-1", deps=deps)

    assert out == [rescored]
    assert calls["args"][0] is raw
    assert calls["args"][3] == tmp_path / "proj" / "run-1"


def test_scored_run_dimensions_skips_rescore_without_suppressions(tmp_path):
    from quodeq.services.scoring import ScoringDeps, scored_run_dimensions

    raw = _dim()
    deps = ScoringDeps(
        read_run_data=lambda root, p, r: [raw],
        dismissed_keys=lambda pd: set(),
        deleted_keys=lambda pd: set(),
        rescore_dimension=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not rescore")),
    )
    assert scored_run_dimensions(tmp_path, "proj", "run-1", deps=deps) == [raw]


def test_rescore_accumulated_uses_injected_rescorer(tmp_path):
    from quodeq.services.scoring import ScoringDeps, rescore_accumulated

    accumulated = {
        "dimensions": [{"dimension": "security", "fromRunId": "run-1",
                        "overallScore": "5.0/10", "violations": []}],
        "summary": {"dimensionsCount": 1},
    }
    seen = {}

    def fake_runs_rescore(dims, root, project, dismissed, deleted, *, params):
        seen["dims"] = dims
        return {"security": {"overallScore": "8.0/10", "overallGrade": "Good"}}

    deps = ScoringDeps(
        dismissed_keys=lambda pd: {("R1", "a.py", 1)},
        deleted_keys=lambda pd: set(),
        rescore_runs_by_dimension=fake_runs_rescore,
    )
    out = rescore_accumulated(accumulated, tmp_path, "proj", deps=deps)

    assert seen["dims"] == accumulated["dimensions"]
    assert out["dimensions"][0]["overallScore"] == "8.0/10"


def test_none_deps_defaults_to_production_behavior(tmp_path):
    """deps=None resolves every field to the module's production callable,
    so existing callers and (transitionally) namespace patches see no change."""
    from quodeq.services import scoring

    (tmp_path / "proj").mkdir()
    import pytest

    with pytest.raises(FileNotFoundError):
        scoring.get_scores_raw(tmp_path, "proj", "missing-run")
