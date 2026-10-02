"""Where the GitHub token quodeq obtained lives: the OS keyring, like provider keys.

Reuses ``ai_provider.store_api_key`` / ``get_api_key_secure`` under the entry
name ``github_account`` so the keyring-then-opt-in-cleartext policy, its
error and its tests are shared, not copied. The value is a small JSON
document, never the bare token, so the login and expiry travel with it.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum

import keyring
import keyring.errors

from quodeq.config import ai_provider
from quodeq.config.ai_provider import KEYRING_SERVICE, get_api_key_secure, store_api_key
from quodeq.config.paths import ConfigPaths
from quodeq.shared.logging import log_debug

ACCOUNT_KEY = "github_account"  # keyring entry; cleartext fallback var is GITHUB_ACCOUNT_API_KEY
_CLEARTEXT_PREFIX = f"export {ACCOUNT_KEY.upper()}_API_KEY="
_OWNER_RW_PERMS = 0o600
_REQUIRED_FIELDS = ("token", "login", "method")


class TokenMethod(StrEnum):
    """How the stored token was obtained."""

    OAUTH_DEVICE = "oauth_device"
    PASTED = "pasted"


@dataclass(frozen=True)
class GitHubAccount:
    """A stored GitHub token with the login it belongs to and its lifetime."""

    token: str
    login: str
    method: TokenMethod
    expires_at: float | None = None  # epoch seconds; None = does not expire
    refresh_token: str | None = None
    scope: str = ""


def store_account(account: GitHubAccount, paths: ConfigPaths | None = None) -> tuple[bool, bool]:
    """Persist *account*. Returns (stored, secure) like ``store_api_key`` and
    raises ``PlaintextKeyRefusedError`` under the same conditions."""
    return store_api_key(ACCOUNT_KEY, json.dumps(asdict(account), sort_keys=True), paths)


def load_account(paths: ConfigPaths | None = None) -> GitHubAccount | None:
    """The stored account, or None when absent or unreadable."""
    raw = get_api_key_secure(ACCOUNT_KEY, paths)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError as exc:
        log_debug(f"github account entry is not JSON: {exc}")
        return None
    if not isinstance(data, dict) or any(k not in data for k in _REQUIRED_FIELDS):
        return None
    try:
        return GitHubAccount(
            token=str(data["token"]), login=str(data["login"]), method=TokenMethod(data["method"]),
            expires_at=data.get("expires_at"), refresh_token=data.get("refresh_token"),
            scope=str(data.get("scope", "")),
        )
    except ValueError as exc:
        log_debug(f"github account entry has an unknown method: {exc}")
        return None


def delete_account(paths: ConfigPaths | None = None) -> None:
    """Forget the stored account everywhere it may live. Idempotent."""
    try:
        keyring.delete_password(KEYRING_SERVICE, ACCOUNT_KEY)
    except (keyring.errors.KeyringError, OSError, RuntimeError) as exc:
        log_debug(f"keyring delete for '{ACCOUNT_KEY}' skipped: {exc}")
    _drop_cleartext_export(paths if paths is not None else ai_provider.default_paths())


def _drop_cleartext_export(paths: ConfigPaths) -> None:
    """Remove the cleartext fallback line. ``store_api_key(key, "")`` cannot do
    it: an empty value leaves the existing export in place."""
    env_file = paths.env_file
    if env_file is None or not env_file.exists():
        return
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if not ln.strip().startswith(_CLEARTEXT_PREFIX)]
        if len(kept) == len(lines):
            return
        env_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
        os.chmod(env_file, _OWNER_RW_PERMS)
    except OSError as exc:
        log_debug(f"cleartext delete for '{ACCOUNT_KEY}' failed: {exc}")


def is_expired(account: GitHubAccount, now: float) -> bool:
    """True when the token has an expiry and *now* has reached it."""
    return account.expires_at is not None and now >= account.expires_at
