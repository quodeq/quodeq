"""The quodeq GitHub OAuth App: public client id and GitHub endpoints.

The device flow needs only the client id (no secret), so it is safe in
source. Forks register their own app and set QUODEQ_GITHUB_CLIENT_ID.
An empty id means sign-in is not configured; the route answers 503.
"""
from __future__ import annotations

from collections.abc import Mapping

from quodeq.shared.env_resolve import resolve_env

GITHUB_HOST = "github.com"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"
# Private clones and publishing (push) both need `repo`; nothing less covers either.
GITHUB_OAUTH_SCOPE = "repo"

GITHUB_CLIENT_ID_ENV = "QUODEQ_GITHUB_CLIENT_ID"
# Filled in once the quodeq org registers the OAuth App (Settings > Developer
# settings > OAuth Apps, "Enable Device Flow" on). Empty until then.
DEFAULT_GITHUB_CLIENT_ID = ""


def github_client_id(env: Mapping[str, str] | None = None) -> str:
    """The OAuth client id: the env override when set and non-blank, else the default."""
    raw = resolve_env(env).get(GITHUB_CLIENT_ID_ENV, "").strip()
    return raw or DEFAULT_GITHUB_CLIENT_ID
