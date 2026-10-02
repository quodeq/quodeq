"""Routes that clone, push or fetch walk the real access ladder.

Only the probe (and gh / the stored account) is faked, by the autouse
``_ambient_access`` fixture in conftest.py, so these tests see the ladder's
call order: the SSRF guard must answer before any probe runs.
"""
from __future__ import annotations

import json

import pytest

from quodeq.config.github_account import GitHubAccount, TokenMethod
from quodeq.data.fs.git_access_probe import ProbeResult
from quodeq.services.github_access import AccessMethod, resolve_access
from quodeq.shared.git_errors import GitFailureKind
from tests.api._routes_shared_fixtures import (  # noqa: F401 -- fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)

_PRIVATE_URLS = [
    "https://127.0.0.1/x/y.git",
    "https://169.254.169.254/latest/meta",
    "ssh://git@10.0.0.1/x/y.git",
]
_ACCT = GitHubAccount(token="gho_stored", login="v", method=TokenMethod.PASTED)


def _token_probe(monkeypatch, ambient: GitFailureKind):
    """Ambient git answers *ambient*; any token-carrying env reaches the repo."""
    calls: list[str] = []

    def probe(url, *, env=None, **_kwargs):
        calls.append(url)
        has_token = bool((env or {}).get("GIT_CONFIG_VALUE_0"))
        return ProbeResult(GitFailureKind.OK if has_token else ambient)

    monkeypatch.setattr("quodeq.services.github_access.probe_remote", probe)
    monkeypatch.setattr("quodeq.services.github_access.load_account", lambda: _ACCT)
    return calls


def _configure(tmp_path, url: str) -> None:
    (tmp_path / "shared.json").write_text(json.dumps({"url": url}))


@pytest.mark.parametrize("url", _PRIVATE_URLS)
def test_create_project_refuses_private_urls_before_probing(client, url, _ambient_access):
    resp = client.post("/api/projects", json={"repo": url, "ephemeral": True}, headers=_ORIGIN)
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_URL"
    assert _ambient_access == []


def test_create_project_refuses_cleartext_http_before_probing(client, _ambient_access):
    resp = client.post("/api/projects", json={"repo": "http://github.com/o/r.git", "ephemeral": True}, headers=_ORIGIN)
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_REPO_URL"
    assert _ambient_access == []


@pytest.mark.parametrize("url", [*_PRIVATE_URLS, "http://github.com/o/r.git"])
def test_connect_refuses_private_urls_before_probing(client, url, _ambient_access):
    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_URL"
    assert _ambient_access == []


@pytest.mark.parametrize("url", [*_PRIVATE_URLS, "http://github.com/o/r.git"])
def test_publish_refuses_private_urls_before_probing(client, tmp_path, monkeypatch, url, _ambient_access):
    _configure(tmp_path, url)
    started = []
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: started.append(a))
    resp = client.post("/api/projects/proj-a/publish", headers=_ORIGIN)
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_URL"
    assert _ambient_access == [] and started == []


def test_publish_unreachable_is_access_400_and_never_starts(client, tmp_path, monkeypatch):
    _configure(tmp_path, "https://github.com/t/r.git")
    monkeypatch.setattr(
        "quodeq.services.github_access.probe_remote",
        lambda url, **_kw: ProbeResult(GitFailureKind.NOT_FOUND, "remote: Repository not found."),
    )
    started = []
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: started.append(a))
    resp = client.post("/api/projects/proj-a/publish", headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "ACCESS_NOT_FOUND" and body["kind"] == "not_found" and body["isGitHub"] is True
    assert started == []


def test_connect_ssh_url_reachable_only_by_token_is_use_https(client, monkeypatch):
    _token_probe(monkeypatch, GitFailureKind.AUTH_REQUIRED)
    started = []
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_connect", lambda url, **kw: started.append(url))
    resp = client.put("/api/shared/config", json={"url": "git@github.com:t/r.git"}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "ACCESS_USE_HTTPS" and body["kind"] == "use_https" and body["detail"] == ""
    assert body["cloneUrl"] == "https://github.com/t/r.git" and body["host"] == "github.com" and body["isGitHub"] is True
    assert started == []


def test_refresh_runs_under_the_cached_token_env(client, tmp_path, monkeypatch):
    url = "https://github.com/t/r.git"
    _configure(tmp_path, url)
    calls = _token_probe(monkeypatch, GitFailureKind.NOT_FOUND)
    access = resolve_access(url)  # what connect did earlier in this process
    assert access.method is AccessMethod.QUODEQ
    calls.clear()
    seen = {}

    def fake_refresh(u, env=None):
        seen.update(url=u, env=env)
        return True, ""

    monkeypatch.setattr("quodeq.api.routes_shared_config.refresh_shared_clone", fake_refresh)
    assert client.post("/api/shared/refresh", headers=_ORIGIN).status_code == 200
    assert seen == {"url": url, "env": access.env} and calls == []  # cached: no probe


def test_refresh_after_restart_walks_the_ladder_once(client, tmp_path, monkeypatch):
    url = "https://github.com/t/r.git"
    _configure(tmp_path, url)
    calls = _token_probe(monkeypatch, GitFailureKind.NOT_FOUND)
    envs = []
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.refresh_shared_clone", lambda u, env=None: envs.append(env) or (True, ""),
    )
    client.post("/api/shared/refresh", headers=_ORIGIN)
    assert envs[0] and envs[0].get("GIT_CONFIG_VALUE_0") and len(calls) == 2  # ambient, then the token
