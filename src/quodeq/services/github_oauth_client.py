"""GitHub OAuth device flow and user lookup over urllib. No new dependency.

Every request carries an explicit timeout and `Accept: application/json`.
Network failures surface as GitHubUnreachable; the caller decides the wire
code. The client secret is never needed: device-flow tokens refresh without it.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from quodeq.config.github_app import GITHUB_ACCESS_TOKEN_URL, GITHUB_API_USER_URL, GITHUB_DEVICE_CODE_URL

_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_REFRESH_GRANT = "refresh_token"
_SCOPES_HEADER = "x-oauth-scopes"
_HTTP_UNAUTHORIZED = 401
_HTTP_CLIENT_ERROR_MIN = 400
_HTTP_SERVER_ERROR_MIN = 500
_DEFAULT_TIMEOUT_S = 20


class GitHubUnreachable(Exception):
    """GitHub did not answer (DNS, connection, timeout, 5xx)."""


class GitHubRefused(Exception):
    """GitHub answered a 4xx that is not a token problem (rate limit, SSO block, bad request, not found)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"GitHub answered {status}")
        self.status = status


class TokenRejected(Exception):
    """GitHub answered 401 to the token: invalid, revoked or SSO-unauthorized."""


class PollKind(StrEnum):
    """Outcome of one device-flow token poll."""
    GRANTED = "granted"
    PENDING = "pending"
    SLOW_DOWN = "slow_down"
    EXPIRED = "expired"
    DENIED = "denied"
    FAILED = "failed"


_POLL_ERRORS = {
    "authorization_pending": PollKind.PENDING,
    "slow_down": PollKind.SLOW_DOWN,
    "expired_token": PollKind.EXPIRED,
    "access_denied": PollKind.DENIED,
}


@dataclass(frozen=True)
class DeviceCode:
    """Device and user codes handed out by GitHub."""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class TokenGrant:
    """An access token, with its optional expiry and refresh token."""
    access_token: str
    scope: str
    expires_in: int | None
    refresh_token: str | None


@dataclass(frozen=True)
class TokenPoll:
    """One poll result: its kind, plus the grant when granted."""
    kind: PollKind
    grant: TokenGrant | None = None
    description: str = ""


@dataclass(frozen=True)
class UserInfo:
    """The signed-in login and the scopes GitHub reports for the token."""
    login: str
    scopes: tuple[str, ...] | None  # None: no X-OAuth-Scopes header (fine-grained PAT)


def _grant(payload: dict) -> TokenGrant:
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise _malformed()
    return TokenGrant(
        access_token=token, scope=str(payload.get("scope", "")),
        expires_in=payload.get("expires_in"), refresh_token=payload.get("refresh_token"),
    )


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("not text")
    return value


def _malformed() -> GitHubUnreachable:
    return GitHubUnreachable("malformed response from GitHub")


class GitHubOAuthClient:
    """Thin urllib client for the device flow, user lookup and refresh."""
    def __init__(self, *, opener: Callable = urllib.request.urlopen, timeout_s: int = _DEFAULT_TIMEOUT_S) -> None:
        self._open = opener
        self._timeout = timeout_s

    def _call(self, url: str, *, form: dict[str, str] | None = None, token: str | None = None) -> tuple[dict, dict]:
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
        req.add_header("Accept", "application/json")
        if token is not None:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with self._open(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8") or "{}")
                headers = {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            if exc.code == _HTTP_UNAUTHORIZED and token is not None:
                raise TokenRejected(f"GitHub answered {exc.code}") from exc
            if _HTTP_CLIENT_ERROR_MIN <= exc.code < _HTTP_SERVER_ERROR_MIN:
                raise GitHubRefused(exc.code) from exc
            raise GitHubUnreachable(f"GitHub answered {exc.code}") from exc
        except ValueError as exc:
            raise _malformed() from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubUnreachable(str(exc)) from exc
        if not isinstance(payload, dict):
            raise _malformed()
        return payload, headers

    def request_device_code(self, client_id: str, scope: str) -> DeviceCode:
        """Start the device flow and return the codes to show the user."""
        payload, _ = self._call(GITHUB_DEVICE_CODE_URL, form={"client_id": client_id, "scope": scope})
        try:
            return DeviceCode(
                device_code=_text(payload["device_code"]), user_code=_text(payload["user_code"]),
                verification_uri=_text(payload["verification_uri"]),
                expires_in=int(payload["expires_in"]), interval=int(payload["interval"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise _malformed() from exc

    def poll_token(self, client_id: str, device_code: str) -> TokenPoll:
        """Poll once for the token and classify the answer."""
        payload, _ = self._call(
            GITHUB_ACCESS_TOKEN_URL,
            form={"client_id": client_id, "device_code": device_code, "grant_type": _DEVICE_GRANT},
        )
        if "access_token" in payload:
            return TokenPoll(PollKind.GRANTED, _grant(payload))
        error = str(payload.get("error", ""))
        return TokenPoll(_POLL_ERRORS.get(error, PollKind.FAILED), description=str(payload.get("error_description", "")))

    def fetch_user(self, token: str) -> UserInfo:
        """Look up the token's login and scopes; raises TokenRejected on 401."""
        payload, headers = self._call(GITHUB_API_USER_URL, token=token)
        raw = headers.get(_SCOPES_HEADER)
        scopes = tuple(s.strip() for s in raw.split(",") if s.strip()) if raw is not None else None
        return UserInfo(login=str(payload.get("login", "")), scopes=scopes)

    def refresh(self, client_id: str, refresh_token: str) -> TokenGrant:
        """Exchange a refresh token for a new grant; raises TokenRejected if refused."""
        payload, _ = self._call(
            GITHUB_ACCESS_TOKEN_URL,
            form={"client_id": client_id, "refresh_token": refresh_token, "grant_type": _REFRESH_GRANT},
        )
        if "access_token" not in payload:
            raise TokenRejected(str(payload.get("error_description") or payload.get("error") or "refresh refused"))
        return _grant(payload)
