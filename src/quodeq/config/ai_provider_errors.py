"""Errors ``config.ai_provider`` raises to callers that must tell them apart."""
from __future__ import annotations

from quodeq.config.credentials_env import ALLOW_PLAINTEXT_KEY_ENV

# A key only reaches the env file after the keyring failed (store_api_key),
# so that is the situation this message describes.
PLAINTEXT_KEY_REFUSED_MESSAGE = (
    "No OS keyring is available, so the key was not saved. Export {env_var} "
    f"in your shell instead, or set {ALLOW_PLAINTEXT_KEY_ENV}=1 to store it "
    "in .quodeq.env (mode 0600)."
)


class PlaintextKeyRefusedError(Exception):
    """No keyring and no ``QUODEQ_ALLOW_PLAINTEXT_KEY``: the key was not written.

    *env_var* is the variable the user can export instead.
    """

    def __init__(self, env_var: str) -> None:
        super().__init__(PLAINTEXT_KEY_REFUSED_MESSAGE.format(env_var=env_var))
        self.env_var = env_var
