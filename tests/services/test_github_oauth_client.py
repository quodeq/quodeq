"""GitHubOAuthClient against a fake opener: device code, poll outcomes, user, refresh."""
from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message

import pytest

from quodeq.config.github_app import GITHUB_ACCESS_TOKEN_URL, GITHUB_API_USER_URL, GITHUB_DEVICE_CODE_URL
from quodeq.services.github_oauth_client import (
    GitHubOAuthClient, GitHubRefused, GitHubUnreachable, PollKind, TokenRejected, UserInfo,
)


class _Response(io.BytesIO):
    def __init__(self, payload, headers=None):
        super().__init__(json.dumps(payload).encode())
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(responses):
    seen = []

    def open_(req, timeout=None):
        seen.append((req.full_url, req.data, dict(req.header_items()), timeout))
        reply = responses.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    open_.seen = seen
    return open_


def test_request_device_code_posts_client_id_and_scope():
    opener = _opener([_Response({"device_code": "d", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "expires_in": 900, "interval": 5})])
    code = GitHubOAuthClient(opener=opener).request_device_code("Iv1.x", "repo")
    url, data, headers, timeout = opener.seen[0]
    assert url == GITHUB_DEVICE_CODE_URL and timeout == 20
    assert b"client_id=Iv1.x" in data and b"scope=repo" in data
    assert headers["Accept"] == "application/json"
    assert (code.user_code, code.interval, code.expires_in) == ("ABCD-1234", 5, 900)


@pytest.mark.parametrize("error,kind", [
    ("authorization_pending", PollKind.PENDING),
    ("slow_down", PollKind.SLOW_DOWN),
    ("expired_token", PollKind.EXPIRED),
    ("access_denied", PollKind.DENIED),
    ("incorrect_device_code", PollKind.FAILED),
])
def test_poll_token_maps_github_errors(error, kind):
    opener = _opener([_Response({"error": error, "error_description": "why"})])
    poll = GitHubOAuthClient(opener=opener).poll_token("Iv1.x", "d")
    assert poll.kind is kind and poll.grant is None and poll.description == "why"
    assert opener.seen[0][0] == GITHUB_ACCESS_TOKEN_URL
    assert b"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code" in opener.seen[0][1]


def test_poll_token_granted_with_and_without_expiry():
    opener = _opener([
        _Response({"access_token": "gho_a", "scope": "repo", "token_type": "bearer"}),
        _Response({"access_token": "ghu_b", "scope": "repo", "expires_in": 28800, "refresh_token": "ghr_c"}),
    ])
    client = GitHubOAuthClient(opener=opener)
    first = client.poll_token("Iv1.x", "d")
    assert first.kind is PollKind.GRANTED and first.grant.access_token == "gho_a" and first.grant.expires_in is None
    second = client.poll_token("Iv1.x", "d")
    assert second.grant.expires_in == 28800 and second.grant.refresh_token == "ghr_c"


def test_fetch_user_reads_login_and_scopes():
    opener = _opener([_Response({"login": "victor"}, headers={"X-OAuth-Scopes": "repo, read:org"})])
    info = GitHubOAuthClient(opener=opener).fetch_user("gho_a")
    assert info == UserInfo("victor", ("repo", "read:org"))
    assert opener.seen[0][2]["Authorization"] == "Bearer gho_a"
    assert opener.seen[0][0] == GITHUB_API_USER_URL


def test_fetch_user_fine_grained_token_has_no_scopes_header():
    opener = _opener([_Response({"login": "victor"})])
    assert GitHubOAuthClient(opener=opener).fetch_user("github_pat_x") == UserInfo("victor", None)


def test_fetch_user_401_is_token_rejected():
    err = urllib.error.HTTPError(GITHUB_API_USER_URL, 401, "Unauthorized", Message(), io.BytesIO(b"{}"))
    with pytest.raises(TokenRejected):
        GitHubOAuthClient(opener=_opener([err])).fetch_user("bad")


def test_network_failure_is_unreachable():
    with pytest.raises(GitHubUnreachable):
        GitHubOAuthClient(opener=_opener([urllib.error.URLError("dns")])).request_device_code("Iv1.x", "repo")
    with pytest.raises(GitHubUnreachable):
        GitHubOAuthClient(opener=_opener([TimeoutError()])).fetch_user("t")


def test_refresh_posts_refresh_grant_without_a_secret():
    opener = _opener([_Response({"access_token": "ghu_new", "scope": "repo", "expires_in": 28800, "refresh_token": "ghr_new"})])
    grant = GitHubOAuthClient(opener=opener).refresh("Iv1.x", "ghr_old")
    data = opener.seen[0][1]
    assert b"grant_type=refresh_token" in data and b"refresh_token=ghr_old" in data and b"client_secret" not in data
    assert grant.access_token == "ghu_new"


def _http_error(code):
    return urllib.error.HTTPError("https://x", code, "err", Message(), io.BytesIO(b"{}"))


@pytest.mark.parametrize("payload", [{}, {"device_code": "d"}, {"device_code": None, "user_code": "u", "verification_uri": "v", "expires_in": 1, "interval": 1}, {"device_code": "d", "user_code": "u", "verification_uri": "v", "expires_in": "soon", "interval": 1}])
def test_malformed_device_code_is_unreachable(payload):
    with pytest.raises(GitHubUnreachable, match="malformed"):
        GitHubOAuthClient(opener=_opener([_Response(payload)])).request_device_code("Iv1.x", "repo")


def test_granted_with_non_string_token_is_unreachable():
    with pytest.raises(GitHubUnreachable, match="malformed"):
        GitHubOAuthClient(opener=_opener([_Response({"access_token": 5})])).poll_token("Iv1.x", "d")


def test_403_on_user_is_refused_with_status():
    with pytest.raises(GitHubRefused) as info:
        GitHubOAuthClient(opener=_opener([_http_error(403)])).fetch_user("t")
    assert info.value.status == 403


def test_401_without_a_token_is_refused_not_rejected():
    with pytest.raises(GitHubRefused):
        GitHubOAuthClient(opener=_opener([_http_error(401)])).request_device_code("bad", "repo")


def test_502_is_unreachable():
    with pytest.raises(GitHubUnreachable):
        GitHubOAuthClient(opener=_opener([_http_error(502)])).fetch_user("t")


def test_non_object_body_is_unreachable():
    with pytest.raises(GitHubUnreachable, match="malformed"):
        GitHubOAuthClient(opener=_opener([_Response([])])).fetch_user("t")


def test_refresh_refusal_is_token_rejected():
    opener = _opener([_Response({"error": "bad_refresh_token"})])
    with pytest.raises(TokenRejected):
        GitHubOAuthClient(opener=opener).refresh("Iv1.x", "ghr_old")
