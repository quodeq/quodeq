"""A complete run's scoped version is a pure function of its immutable key set
and the suppression state, so it is served from memory while that state holds.

Before this memo every project-list rebuild and scores call reloaded and
decoded every run's key blobs (158 MB across five projects here) to recompute
versions that had not changed.
"""
import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.services import run_keys as run_keys_mod
from quodeq.services import score_cache as sc
from quodeq.services.trend_fetcher import _make_version_for
from quodeq.services.score_cache import VersionInputs, per_run_versions
from quodeq.services.suppression_keys import SuppressionKeys

_NO_KEYS = SuppressionKeys(set(), set())


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))


def _run_with_finding(project_dir, run_id, file="a.py"):
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True)
    with open_evaluation_db(run_dir) as conn:
        conn.execute(
            "INSERT INTO findings (practice_id, dimension, requirement, verdict, "
            "severity, file, line, dedup_key) VALUES ('P1','security','R1','violation',"
            "'major',?,1,'k1')",
            (file,),
        )
        conn.commit()
    return run_dir


def _forbid_key_reads(monkeypatch):
    def _no_read(run_dir):
        raise AssertionError(f"run key sets re-read for {run_dir}")

    def _no_load(project):
        raise AssertionError(f"cached run keys reloaded for {project}")

    monkeypatch.setattr(run_keys_mod, "read_run_key_sets", _no_read)
    monkeypatch.setattr(sc, "load_run_keys_or_empty", _no_load)


def test_unchanged_state_serves_complete_runs_from_memory(tmp_path, monkeypatch):
    pd = tmp_path / "proj"
    _run_with_finding(pd, "r1")
    _run_with_finding(pd, "r2", file="b.py")
    runs = [("r1", "complete"), ("r2", "complete")]
    first = per_run_versions(pd, "proj", DEFAULT_PARAMS, runs, keys=_NO_KEYS)

    _forbid_key_reads(monkeypatch)
    again = per_run_versions(pd, "proj", DEFAULT_PARAMS, runs, keys=_NO_KEYS)
    assert again == first


def test_a_dismissal_touching_the_run_changes_its_version(tmp_path):
    pd = tmp_path / "proj"
    _run_with_finding(pd, "r1")
    base = per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "complete")], keys=_NO_KEYS)
    touched = per_run_versions(
        pd, "proj", DEFAULT_PARAMS, [("r1", "complete")],
        keys=SuppressionKeys({("R1", "a.py", 1)}, set()))
    assert base[0][2] != touched[0][2]
    # Back to the earlier state: the earlier version, not a third one.
    back = per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "complete")], keys=_NO_KEYS)
    assert back == base


def test_non_complete_runs_are_still_read_every_call(tmp_path, monkeypatch):
    pd = tmp_path / "proj"
    _run_with_finding(pd, "r1")
    per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "cancelled")], keys=_NO_KEYS)

    seen = []
    real = run_keys_mod.read_run_key_sets

    def counting(run_dir):
        seen.append(run_dir)
        return real(run_dir)

    monkeypatch.setattr(run_keys_mod, "read_run_key_sets", counting)
    per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "cancelled")], keys=_NO_KEYS)
    assert seen == [pd / "r1"]


def test_trend_version_for_reuses_the_memo_for_cacheable_runs(tmp_path, monkeypatch):
    pd = tmp_path / "proj"
    _run_with_finding(pd, "r1")
    inputs = VersionInputs.of(DEFAULT_PARAMS, set(), set())
    first = _make_version_for(pd, "proj", inputs, lambda: {}, {"r1"})("r1")

    _forbid_key_reads(monkeypatch)

    def _no_load():
        raise AssertionError("cached run keys loaded although every run was memoized")

    again = _make_version_for(pd, "proj", inputs, _no_load, {"r1"})("r1")
    assert again == first


def test_trend_version_for_loads_keys_lazily_and_once(tmp_path):
    pd = tmp_path / "proj"
    _run_with_finding(pd, "r1")
    _run_with_finding(pd, "r2", file="b.py")
    loads = []

    def load():
        loads.append(1)
        return {}

    # Not cacheable: nothing memoized, so the loader runs, but only once per fetcher.
    version_for = _make_version_for(
        pd, "proj", VersionInputs.of(DEFAULT_PARAMS, set(), set()), load, set())
    assert loads == []
    version_for("r1")
    version_for("r2")
    assert loads == [1]
