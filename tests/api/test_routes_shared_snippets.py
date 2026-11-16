"""PUT /api/shared/snippets: the shared repository's opt-in to code snippets, read by publish."""
from __future__ import annotations

import json

from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)

_URL = "git@github.com:t/r.git"


def _connect(tmp_path, **extra):
    (tmp_path / "shared.json").write_text(json.dumps({"url": _URL, **extra}))


def test_snippets_are_off_until_opted_in(client, tmp_path):
    _connect(tmp_path)
    assert client.get("/api/shared/status").get_json()["withSnippets"] is False


def test_opt_in_is_saved_and_reported(client, tmp_path):
    _connect(tmp_path)
    resp = client.put("/api/shared/snippets", json={"withSnippets": True}, headers=_ORIGIN)
    assert resp.status_code == 200
    assert client.get("/api/shared/status").get_json()["withSnippets"] is True
    assert json.loads((tmp_path / "shared.json").read_text()) == {"url": _URL, "with_snippets": True}


def test_non_boolean_is_refused(client, tmp_path):
    _connect(tmp_path)
    resp = client.put("/api/shared/snippets", json={"withSnippets": "yes"}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_INPUT"


def test_no_repository_no_choice(client):
    resp = client.put("/api/shared/snippets", json={"withSnippets": True}, headers=_ORIGIN)
    assert resp.status_code == 400


def test_publish_passes_the_choice(client, tmp_path, monkeypatch):
    _connect(tmp_path, with_snippets=True)
    seen = {}
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.start_publish",
        lambda *a, **kw: seen.update(kw) or "started",
    )
    assert client.post("/api/projects/some-proj/publish", headers=_ORIGIN).status_code == 202
    assert seen["with_snippets"] is True
