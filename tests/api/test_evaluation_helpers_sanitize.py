"""Tests for _sanitize_url in _evaluation_helpers.py.

Mirrors the adversarial cases in tests/shared/test_repo_remote_url.py's
test_normalize_strips_userinfo_containing_a_slash (the same algorithm,
ported here with _sanitize_url's own return shape: scheme + "***@" +
host/path, credentials masked rather than dropped).
"""
from __future__ import annotations

from quodeq.api._evaluation_helpers import _sanitize_url

from tests._credential_urls import SLASH_CREDENTIAL_SECRETS, SLASH_IN_CREDENTIAL_URLS


def test_sanitize_url_simple_user_pass():
    assert _sanitize_url("https://user:token@host/repo.git") == "https://***@host/repo.git"


def test_sanitize_url_token_only():
    assert _sanitize_url("https://ghp_supersecrettoken@github.com/org/repo.git") == (
        "https://***@github.com/org/repo.git"
    )


def test_sanitize_url_no_credentials_present():
    assert _sanitize_url("https://github.com/org/repo.git") == "https://github.com/org/repo.git"


def test_sanitize_url_leaves_a_legitimate_path_at_sign_alone():
    """An @ after the authority (a path segment) must not be masked."""
    url = "https://git.example.com/~user@host/repo.git"
    assert _sanitize_url(url) == url


def test_sanitize_url_masks_userinfo_containing_a_slash():
    """A "/" inside the credential must not truncate the userinfo search window.

    Cases and rationale: tests/_credential_urls.py.
    """
    for leaky, tail in SLASH_IN_CREDENTIAL_URLS:
        sanitized = _sanitize_url(leaky)
        assert sanitized == f"https://***@{tail}"
        for secret in SLASH_CREDENTIAL_SECRETS:
            assert secret not in sanitized
