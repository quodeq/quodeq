"""Unit tests for the rescore_project_run use case (no Flask).

The point of extracting services.rescore_run from the /api/rescore route is
that the "which run counts as latest" rule and the not-found/invalid
distinctions are plain function behavior. These tests exercise exactly that:
directory resolution runs against real tmp_path trees, while the heavier
collaborators (list_runs, read_run_data, rescore_dimensions, the
dismissed/deleted/suppression loaders) are patched at the module seam.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.services import rescore_run
from quodeq.services.rescore_run import (
    RescoreOutcome,
    rescore_project_run,
    resolve_latest_run_id,
)

_PROJECT = "test-project"
_RUN = "run-1"


def _run_info(run_id: str) -> SimpleNamespace:
    return SimpleNamespace(run_id=run_id, date_iso="2026-04-02", date_label="Apr 2")


@pytest.fixture
def reports_root(tmp_path: Path) -> Path:
    (tmp_path / _PROJECT / _RUN).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def quiet_collaborators(monkeypatch) -> dict:
    """Patch loaders + rescore so the use case runs without run artifacts."""
    calls: dict = {}

    def fake_read_run_data(root, project, run_id):
        calls["read_run_data"] = (root, project, run_id)
        return []

    def fake_rescore(dimensions, dismissed, deleted, *, run_dir, rules):
        calls["rescore"] = {"run_dir": run_dir, "rules": rules}
        return {"dimensions": [], "summary": {"dimensionsCount": 0}}

    monkeypatch.setattr(rescore_run, "read_run_data", fake_read_run_data)
    monkeypatch.setattr(rescore_run, "rescore_dimensions", fake_rescore)
    monkeypatch.setattr(rescore_run, "load_dismissed_keys", lambda project_dir: set())
    monkeypatch.setattr(rescore_run, "load_deleted_keys", lambda project_dir: set())
    monkeypatch.setattr(rescore_run, "load_suppression_rules", lambda project_dir: ())
    return calls


def test_latest_run_is_the_first_of_list_runs_newest_first(reports_root, quiet_collaborators, monkeypatch):
    """"latest" (and empty) resolve to list_runs(limit=1)[0].run_id."""
    seen: dict = {}

    def fake_list_runs(root, project, *, limit):
        seen["args"] = (root, project, limit)
        return [_run_info(_RUN)]

    monkeypatch.setattr(rescore_run, "list_runs", fake_list_runs)

    for run_param in ("", "latest"):
        outcome = rescore_project_run(reports_root, _PROJECT, run_param)
        assert outcome.status == "ok"
        assert quiet_collaborators["read_run_data"] == (reports_root, _PROJECT, _RUN)
    assert seen["args"] == (reports_root, _PROJECT, 1)


def test_resolve_latest_run_id_plain_function(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rescore_run, "list_runs",
        lambda root, project, *, limit: [_run_info("newest")],
    )
    assert resolve_latest_run_id(tmp_path, _PROJECT) == "newest"

    monkeypatch.setattr(rescore_run, "list_runs", lambda root, project, *, limit: [])
    assert resolve_latest_run_id(tmp_path, _PROJECT) is None


def test_explicit_run_id_never_consults_list_runs(reports_root, quiet_collaborators, monkeypatch):
    def fail_list_runs(*args, **kwargs):
        raise AssertionError("list_runs must not be called for an explicit run id")

    monkeypatch.setattr(rescore_run, "list_runs", fail_list_runs)
    outcome = rescore_project_run(reports_root, _PROJECT, _RUN)
    assert outcome.status == "ok"
    assert outcome.result == {"dimensions": [], "summary": {"dimensionsCount": 0}}


def test_project_with_no_runs_is_project_not_found(reports_root, monkeypatch):
    monkeypatch.setattr(rescore_run, "list_runs", lambda root, project, *, limit: [])
    outcome = rescore_project_run(reports_root, _PROJECT, "latest")
    assert outcome == RescoreOutcome("project_not_found")


def test_invalid_segments_are_invalid_param(reports_root):
    assert rescore_project_run(reports_root, "../escape", "").status == "invalid_param"
    assert rescore_project_run(reports_root, _PROJECT, "../run").status == "invalid_param"


def test_unknown_project_is_project_not_found(tmp_path):
    outcome = rescore_project_run(tmp_path, "no-such-project", "")
    assert outcome == RescoreOutcome("project_not_found")


def test_missing_run_dir_is_run_not_found(reports_root):
    outcome = rescore_project_run(reports_root, _PROJECT, "no-such-run")
    assert outcome == RescoreOutcome("run_not_found")


def test_missing_run_data_is_run_not_found(reports_root, quiet_collaborators, monkeypatch):
    def raise_missing(root, project, run_id):
        raise FileNotFoundError(f"Run not found: {project}/{run_id}")

    monkeypatch.setattr(rescore_run, "read_run_data", raise_missing)
    outcome = rescore_project_run(reports_root, _PROJECT, _RUN)
    assert outcome == RescoreOutcome("run_not_found")


def test_rescore_receives_the_resolved_run_dir(reports_root, quiet_collaborators):
    outcome = rescore_project_run(reports_root, _PROJECT, _RUN)
    assert outcome.status == "ok"
    assert quiet_collaborators["rescore"]["run_dir"] == reports_root / _PROJECT / _RUN
