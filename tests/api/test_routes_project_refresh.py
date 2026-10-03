"""POST /api/projects/<project>/refresh: outcome to HTTP mapping."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.core.types.working_copy_refresh import RefreshOutcome
from quodeq.services.project_refresh import ProjectRefresh
from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)

_URL = "/api/projects/my-proj/refresh"


def _post(client, result: ProjectRefresh | None):
    with patch("quodeq.api.routes_project_refresh.refresh_project", return_value=result) as refresh:
        resp = client.post(_URL)
    return resp, refresh


def test_updated_reports_commits_and_fetch_time(client):
    result = ProjectRefresh(RefreshOutcome.UPDATED, new_commits=4, last_fetched_at="2026-10-03T10:00:00+00:00")

    resp, refresh = _post(client, result)

    assert resp.status_code == 200
    assert resp.get_json() == {
        "outcome": "updated", "newCommits": 4, "lastFetchedAt": "2026-10-03T10:00:00+00:00",
    }
    assert refresh.call_args.args[2] == "my-proj"


def test_up_to_date_is_a_success(client):
    resp, _ = _post(client, ProjectRefresh(RefreshOutcome.UP_TO_DATE))

    assert resp.status_code == 200
    assert resp.get_json()["outcome"] == "up_to_date"


def test_unknown_project_is_404(client):
    resp, _ = _post(client, None)

    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize(("outcome", "status"), [
    (RefreshOutcome.NOT_REFRESHABLE, 400),
    (RefreshOutcome.BUSY, 409),
    (RefreshOutcome.DIRTY, 409),
    (RefreshOutcome.NO_UPSTREAM, 409),
    (RefreshOutcome.DIVERGED, 409),
    (RefreshOutcome.FETCH_FAILED, 502),
])
def test_refusals_carry_the_outcome_as_code(client, outcome, status):
    resp, _ = _post(client, ProjectRefresh(outcome, detail="git said no"))

    assert resp.status_code == status
    body = resp.get_json()
    assert body["code"] == outcome.name
    assert body["error"]
    assert body["detail"] == "git said no"


def test_malformed_project_segment_is_rejected(client):
    with patch("quodeq.api.routes_project_refresh.refresh_project") as refresh:
        resp = client.post("/api/projects/..%2Fx/refresh")

    assert resp.status_code in (400, 404)
    refresh.assert_not_called()
