from pathlib import Path
import pytest

from quodeq.services.dashboard import (
    build_dashboard, clear_shared_dimension_cache, _SHARED_RUN_DIM_CACHE,
)
from quodeq.services.dismissed import dismiss_finding, dismissed_keys
from quodeq.services.score_cache import score_cache_version
from quodeq.core.scoring.params import DEFAULT_PARAMS
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _versions_in_shared_cache() -> set:
    """Return the suppression-version component of every 4-tuple shared-cache key."""
    return {k[3] for k in _SHARED_RUN_DIM_CACHE if len(k) == 4}


def test_dismiss_produces_a_new_shared_cache_version(tmp_path):
    """After a dismiss, the shared in-memory dim cache is keyed by the project's
    suppression version, so no read path can serve a pre-dismiss entry.

    A dismiss activates the trend fetcher's *heavy* (rescoring) path, which is
    the one that populates ``_SHARED_RUN_DIM_CACHE``. Before the fix its keys
    were 3-tuples with no version component, so ``_versions_in_shared_cache()``
    was empty and this assertion failed. After the fix the key carries the
    suppression hash from ``score_cache_version``.
    """
    reports = tmp_path / "evaluations"
    project = "proj"
    build_projected_run(reports, project, "20260101T000000", {"security": (7.0, "Fair")})

    # Warm on a clean project so nothing but a dismiss can introduce a version.
    build_dashboard(reports, project, run="latest")
    versions_before = _versions_in_shared_cache()

    # ``dismiss_finding(project_dir, finding: dict)`` -- confirmed against
    # src/quodeq/services/dismissed.py; the dict keys are req/file/line.
    dismiss_finding(reports / project, {"req": "R1", "file": "a.py", "line": 1})
    assert dismissed_keys(reports / project), "dismiss did not register"

    build_dashboard(reports, project, run="latest")
    versions_after = _versions_in_shared_cache()

    # A new suppression version key appeared -> the pre-dismiss entry is no longer
    # the one served. Before the fix, keys were 3-tuples with no version, so
    # `_versions_in_shared_cache()` would be empty and this assertion would fail.
    new_versions = versions_after - versions_before
    assert new_versions, "dismiss did not produce a new shared-cache version key"

    # The new key is versioned by the project's actual suppression state.
    expected = score_cache_version(reports / project, DEFAULT_PARAMS)
    assert expected in new_versions, (
        "shared-cache version does not match the project suppression hash"
    )
