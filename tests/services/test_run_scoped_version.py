from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import run_scoped_version


def test_version_changes_only_for_intersecting_suppression():
    run_dismiss = {("R1", "a.py", 1)}
    run_class = {("security", "P1", "a.py")}

    base = run_scoped_version(DEFAULT_PARAMS, run_dismiss, run_class, set(), set())
    # A dismissal NOT present in this run's keys must not change its version.
    unrelated = run_scoped_version(
        DEFAULT_PARAMS, run_dismiss, run_class, {("OTHER", "z.py", 9)}, set())
    assert unrelated == base
    # A dismissal that IS present must change it.
    related = run_scoped_version(
        DEFAULT_PARAMS, run_dismiss, run_class, {("R1", "a.py", 1)}, set())
    assert related != base
    # A delete of this run's class must change it.
    deleted = run_scoped_version(
        DEFAULT_PARAMS, run_dismiss, run_class, set(), {("security", "P1", "a.py")})
    assert deleted != base
