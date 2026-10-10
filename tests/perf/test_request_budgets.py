"""I/O budgets for the dashboard's hot paths.

Performance regressed one fix at a time: each change looked local, while the
same log was replayed and the same reports re-read by more and more code
paths per request. These tests count the reads one
scenario does on a fixed project and hold them to the committed budgets in
``request_budgets.json``. Counts, not timings, so they are deterministic.

A count above its budget fails: find the new read, or justify it and raise
the budget in the same PR. A count below its budget fails too, so an
improvement is locked in: rerun with ``QUODEQ_UPDATE_BUDGETS=1`` and commit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services.dismissed import dismiss_finding
from tests.perf._budget_fixture import LATEST_ONLY, PROJECT, count_io, seed_project

_BUDGETS = Path(__file__).with_name("request_budgets.json")

pytestmark = pytest.mark.real_standards


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    reports = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    seed_project(reports)
    app = create_app(static_dist=None, api_key=None)
    client = app.test_client()
    client.reports = reports
    return client


def _load_overview(client) -> None:
    for url in (f"/api/projects/{PROJECT}/scores", f"/api/projects/{PROJECT}/dashboard?view=overview"):
        assert client.get(url).status_code == 200, url


def _load_dismissed(client) -> None:
    resp = client.get(f"/api/findings/dismissed?project={PROJECT}")
    assert resp.status_code == 200 and len(resp.get_json()) == 1


def _scenarios(client, monkeypatch) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    with count_io(monkeypatch) as cold:
        _load_overview(client)
    out["overview_cold"] = dict(cold)
    with count_io(monkeypatch) as warm:
        _load_overview(client)
    out["overview_warm"] = dict(warm)
    dismiss_finding(client.reports / PROJECT, LATEST_ONLY)
    with count_io(monkeypatch) as after:
        _load_overview(client)
    out["overview_after_dismiss"] = dict(after)
    # The Dismissed tab's listing: the finding sits in the newest run, so the
    # cold lookup opens that run only; the warm one reuses the resolved detail.
    with count_io(monkeypatch) as list_cold:
        _load_dismissed(client)
    out["dismissed_list_cold"] = dict(list_cold)
    with count_io(monkeypatch) as list_warm:
        _load_dismissed(client)
    out["dismissed_list_warm"] = dict(list_warm)
    return out


def test_dashboard_reads_stay_within_budget(client, monkeypatch):
    measured = _scenarios(client, monkeypatch)
    if os.environ.get("QUODEQ_UPDATE_BUDGETS"):
        _BUDGETS.write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip("budgets rewritten")
    budgets = json.loads(_BUDGETS.read_text(encoding="utf-8"))
    over = {
        f"{scenario}.{kind}": (count, budgets.get(scenario, {}).get(kind, 0))
        for scenario, counts in measured.items() for kind, count in counts.items()
        if count > budgets.get(scenario, {}).get(kind, 0)
    }
    assert not over, f"reads over budget (measured, budget): {over}"
    assert measured == budgets, (
        "reads dropped below budget; lock the improvement in with "
        "QUODEQ_UPDATE_BUDGETS=1 uv run pytest tests/perf and commit request_budgets.json"
    )
