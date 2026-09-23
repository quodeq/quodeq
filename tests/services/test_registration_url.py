"""Tests for the pure credential-stripping helper in _registration_url.py.

Mirrors the adversarial cases in tests/shared/test_repo_remote_url.py's
test_normalize_strips_userinfo_containing_a_slash (the same algorithm,
ported here with strip_credentials's own return shape: full URL with
scheme, credentials removed).
"""
from __future__ import annotations

from quodeq.services._registration_url import strip_credentials

from tests._credential_urls import SLASH_CREDENTIAL_SECRETS, SLASH_IN_CREDENTIAL_URLS


def test_strip_credentials_simple_user_pass():
    assert strip_credentials("https://user:token@host/repo.git") == "https://host/repo.git"


def test_strip_credentials_token_only():
    assert strip_credentials("https://ghp_supersecrettoken@github.com/org/repo.git") == (
        "https://github.com/org/repo.git"
    )


def test_strip_credentials_no_credentials_present():
    assert strip_credentials("https://github.com/org/repo.git") == "https://github.com/org/repo.git"


def test_strip_credentials_scp_style_left_untouched():
    """git@host:org/repo.git has no scheme -- the leading git@ is a username
    convention, not a credential, and must survive unchanged."""
    assert strip_credentials("git@github.com:example/myrepo.git") == "git@github.com:example/myrepo.git"


def test_strip_credentials_leaves_a_legitimate_path_at_sign_alone():
    """An @ after the authority (a path segment) must not be stripped."""
    url = "https://git.example.com/~user@host/repo.git"
    assert strip_credentials(url) == url


def test_strip_credentials_removes_userinfo_containing_a_slash():
    """A "/" inside the credential must not truncate the userinfo search window.

    Cases and rationale: tests/_credential_urls.py.
    """
    for leaky, tail in SLASH_IN_CREDENTIAL_URLS:
        stripped = strip_credentials(leaky)
        assert stripped == f"https://{tail}"
        assert "@" not in stripped
        for secret in SLASH_CREDENTIAL_SECRETS:
            assert secret not in stripped
