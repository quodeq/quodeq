"""Differential test: scalar-fast-path trend == heavy-path trend (no dismissals)."""
from pathlib import Path

import pytest

from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.scoring import get_project_scores
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def test_trend_identical_between_fast_and_heavy_paths(tmp_path: Path, monkeypatch) -> None:
    reports = tmp_path / "evaluations"
    build_projected_run(reports, "proj", "20260101T000000",
                        {"security": (7.0, "Fair"), "reliability": (6.0, "Fair")})
    build_projected_run(reports, "proj", "20260102T000000",
                        {"security": (8.5, "Good"), "reliability": (6.5, "Fair")})

    # Fast path (default: no dismissals -> scalar reader).
    fast = get_project_scores(reports, "proj")

    # Force the heavy path for the SAME data by making _make_trend_fetcher
    # return the rescoring fetcher regardless of dismissals.
    import quodeq.services.scoring as scoring
    monkeypatch.setattr(
        scoring, "_make_trend_fetcher",
        lambda rr, p, params=scoring.DEFAULT_PARAMS, cacheable_run_ids=None: (
            scoring._make_rescoring_fetcher(rr, p, params=params)
        ),
    )
    heavy = get_project_scores(reports, "proj")

    assert fast["trend"] == heavy["trend"]
    # And the trend actually has content (guard against both being empty).
    assert len(fast["trend"]) == 2
    assert fast["trend"][0]["numericAverage"] is not None
