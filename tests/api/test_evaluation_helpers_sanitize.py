"""Tests for _sanitize_url in _evaluation_helpers.py.

Mirrors the adversarial cases in tests/shared/test_repo_remote_url.py's
test_normalize_strips_userinfo_containing_a_slash (the same algorithm,
ported here with _sanitize_url's own return shape: scheme + "***@" +
host/path, credentials masked rather than dropped).
"""
from __future__ import annotations

from quodeq.api._evaluation_helpers import _sanitize_url


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
    """A "/" inside the credential must not truncate the userinfo search
    window: real tokens (base64/JWT-derived) commonly contain "/", and
    bounding the search by the first "/" hides the real "@" and lets the
    whole unredacted credential pass through unmasked."""
    cases = {
        "https://user:pa/ss@github.com/org/repo.git": "https://***@github.com/org/repo.git",
        "https://x-access-token:gh_p/xyz@github.com/foo/bar.git": "https://***@github.com/foo/bar.git",
        "https://token/with/slashes@github.com/org/repo.git": "https://***@github.com/org/repo.git",
    }
    for leaky, expected in cases.items():
        sanitized = _sanitize_url(leaky)
        assert sanitized == expected
        assert "pa/ss" not in sanitized and "gh_p/xyz" not in sanitized
        assert "token/with/slashes" not in sanitized
