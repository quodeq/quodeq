"""Environment-based configuration for provider credential storage.

``config.ai_provider`` stores API keys in the OS keyring. Writing a key to
``.quodeq.env`` in cleartext when no keyring is available is opt-in, and the
opt-in is resolved here, lazily per call.
"""
from __future__ import annotations

from collections.abc import Mapping

from quodeq.shared.constants import ENV_TRUTHY
from quodeq.shared.env_resolve import resolve_env

ALLOW_PLAINTEXT_KEY_ENV = "QUODEQ_ALLOW_PLAINTEXT_KEY"

_ALLOW_TRUTHY = frozenset({ENV_TRUTHY, "true", "yes", "on"})


def plaintext_key_fallback_allowed(env: Mapping[str, str] | None = None) -> bool:
    """True when ``QUODEQ_ALLOW_PLAINTEXT_KEY`` is truthy.

    Off by default: without a keyring an API key is not written to disk
    unless the user opts in.
    """
    raw = resolve_env(env).get(ALLOW_PLAINTEXT_KEY_ENV, "")
    return raw.strip().lower() in _ALLOW_TRUTHY
