"""warm_project leaves a project fully readable: card summary, scores payload and the latest Overview.

Regression context: the worker warmed the card summary and the scores
payload, so a card appeared while its Overview still took a cold build on
the first open. A warmed project must open without another loading screen.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services import warmup


def _record(calls, name):
    def fn(*args, **kwargs):
        calls.append((name, args))
        return {}
    return fn


def test_warm_project_builds_the_latest_overview_after_the_summary_and_scores(tmp_path, monkeypatch):
    calls: list[tuple[str, tuple]] = []
    monkeypatch.setattr("quodeq.services._fs_metadata.warm_project_summary", _record(calls, "summary"))
    monkeypatch.setattr("quodeq.services.scoring.get_project_scores", _record(calls, "scores"))
    monkeypatch.setattr("quodeq.services.fs_reports.get_dashboard_overview", _record(calls, "overview"))
    monkeypatch.setattr("quodeq.services.wiring.find_children", lambda root, pid: [])

    warmup.warm_project(str(tmp_path), "p1")

    assert [name for name, _ in calls] == ["summary", "scores", "overview"]
    assert calls[2][1] == (str(tmp_path), "p1", "latest")


def test_warm_project_skips_the_overview_for_a_parent(tmp_path, monkeypatch):
    calls: list[tuple[str, tuple]] = []
    monkeypatch.setattr("quodeq.services._fs_metadata.warm_project_summary", _record(calls, "summary"))
    monkeypatch.setattr("quodeq.services.scoring.get_project_scores", _record(calls, "scores"))
    monkeypatch.setattr("quodeq.services.fs_reports.get_dashboard_overview", _record(calls, "overview"))
    monkeypatch.setattr("quodeq.services.wiring.find_children", lambda root, pid: [Path("child")])

    warmup.warm_project(str(tmp_path), "parent")

    assert [name for name, _ in calls] == ["summary"]


def test_warm_project_survives_an_overview_without_runs(tmp_path, monkeypatch):
    """A missing run must not mark the whole project failed once its card is cached."""
    monkeypatch.setattr("quodeq.services._fs_metadata.warm_project_summary", lambda *a: None)
    monkeypatch.setattr("quodeq.services.scoring.get_project_scores", lambda *a: {})
    monkeypatch.setattr("quodeq.services.wiring.find_children", lambda root, pid: [])

    def missing(*args, **kwargs):
        raise FileNotFoundError("no run")
    monkeypatch.setattr("quodeq.services.fs_reports.get_dashboard_overview", missing)

    warmup.warm_project(str(tmp_path), "p1")  # does not raise
