"""PUT /api/shared/config probes the access ladder before starting the connect job."""
from __future__ import annotations

from quodeq.services import shared_connect_job
from quodeq.services.github_access import AccessMethod, AccessResult
from quodeq.shared.git_errors import GitFailureKind
from tests.api._routes_shared_fixtures import (  # noqa: F401 -- fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)


def test_put_config_probe_failure_is_400_before_the_job(client, monkeypatch):
    unreachable = AccessResult(False, AccessMethod.NONE, GitFailureKind.AUTH_REQUIRED, "denied", "github.com", True, None)
    monkeypatch.setattr("quodeq.api.routes_shared_config.resolve_access", lambda url: unreachable)
    started = []
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_connect", lambda url, **kw: started.append(url))
    resp = client.put("/api/shared/config", json={"url": "https://github.com/t/r.git"}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "ACCESS_AUTH_REQUIRED" and body["kind"] == "auth_required" and body["detail"] == "denied" and body["isGitHub"] is True
    assert started == []


def test_put_config_passes_the_access_env_to_the_job(client, monkeypatch):
    env = {"GIT_CONFIG_COUNT": "1"}
    reachable = AccessResult(True, AccessMethod.QUODEQ, GitFailureKind.OK, "", "github.com", True, env)
    monkeypatch.setattr("quodeq.api.routes_shared_config.resolve_access", lambda url: reachable)
    seen = {}

    def fake_start(url, **kw):
        seen.update(kw)
        return shared_connect_job.ConnectStartResult.STARTED
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_connect", fake_start)
    resp = client.put("/api/shared/config", json={"url": "https://github.com/t/r.git"}, headers=_ORIGIN)
    assert resp.status_code == 202 and seen["env"] == env
