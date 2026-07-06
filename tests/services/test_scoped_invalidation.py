"""Per-run scoped invalidation: a dismiss/delete re-versions only the runs it touches."""
import pytest

from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.score_cache import open_score_cache
from quodeq.services.scoring import get_project_scores
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _insert_finding(run_dir, *, requirement, file, line, dimension, practice_id, dedup_key):
    with open_evaluation_db(run_dir) as conn:
        conn.execute(
            "INSERT INTO findings (practice_id, dimension, requirement, verdict, "
            "severity, file, line, dedup_key) VALUES (?,?,?,?,?,?,?,?)",
            (practice_id, dimension, requirement, "violation", "major", file, line, dedup_key),
        )
        conn.commit()


def _versions(project):
    with open_score_cache() as conn:
        return {(r, v) for r, v in conn.execute(
            "SELECT DISTINCT run_id, version FROM run_scalars WHERE project=?", (project,))}


def test_dismiss_only_reversions_the_touched_run(tmp_path):
    reports = tmp_path / "evaluations"
    r1 = build_projected_run(reports, "proj", "20260101T000000", {"security": (7.0, "Fair")})
    build_projected_run(reports, "proj", "20260102T000000", {"security": (8.0, "Good")})
    # Give run 1 a finding whose key is (R1, a.py, 1) so it (and only it) intersects
    # the dismissal below. Run 2 has no findings -> its key set never intersects.
    _insert_finding(
        r1, requirement="R1", file="a.py", line=1,
        dimension="security", practice_id="P1", dedup_key="k1",
    )

    # Activate the heavy path + populate run_scalars for both runs.
    dismiss_finding(reports / "proj", {"req": "SEED", "file": "seed.py", "line": 0})
    get_project_scores(reports, "proj")
    before = _versions("proj")

    # Dismiss a finding that exists only in the first run's key set.
    dismiss_finding(reports / "proj", {"req": "R1", "file": "a.py", "line": 1})
    get_project_scores(reports, "proj")
    after = _versions("proj")

    changed_runs = {r for (r, v) in after - before}
    # The touched run (run 1) re-versions; the untouched run (run 2) keeps its version.
    assert "20260101T000000" in changed_runs
    assert "20260102T000000" not in changed_runs
