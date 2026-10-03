"""Tests for GET /api/shared/invite."""
from __future__ import annotations

import json

from tests.api._routes_shared_fixtures import client  # noqa: F401 -- pytest fixture

URL = "https://example.invalid/t/r.git"


def test_invite_carries_the_url(client, tmp_path):
    (tmp_path / "shared.json").write_text(json.dumps({"url": URL}))
    resp = client.get("/api/shared/invite")
    assert resp.status_code == 200
    assert resp.get_json() == {"text": f"Open quodeq, choose Connect evaluations repository, paste {URL}"}


def test_invite_unconfigured_is_400(client):
    resp = client.get("/api/shared/invite")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "NO_SHARED_REPO"
