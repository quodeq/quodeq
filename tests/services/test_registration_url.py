"""Tests for the pure credential-stripping helper in _registration_url.py.

Mirrors the adversarial cases in tests/shared/test_repo_remote_url.py's
test_normalize_strips_userinfo_containing_a_slash (the same algorithm,
ported here with _strip_credentials's own return shape: full URL with
scheme, credentials removed).
"""
from __future__ import annotations

from quodeq.services._registration_url import _strip_credentials


def test_strip_credentials_simple_user_pass():
    assert _strip_credentials("https://user:token@host/repo.git") == "https://host/repo.git"


def test_strip_credentials_token_only():
    assert _strip_credentials("https://ghp_supersecrettoken@github.com/org/repo.git") == (
        "https://github.com/org/repo.git"
    )


def test_strip_credentials_no_credentials_present():
    assert _strip_credentials("https://github.com/org/repo.git") == "https://github.com/org/repo.git"


def test_strip_credentials_scp_style_left_untouched():
    """git@host:org/repo.git has no scheme -- the leading git@ is a username
    convention, not a credential, and must survive unchanged."""
    assert _strip_credentials("git@github.com:example/myrepo.git") == "git@github.com:example/myrepo.git"


def test_strip_credentials_leaves_a_legitimate_path_at_sign_alone():
    """An @ after the authority (a path segment) must not be stripped."""
    url = "https://git.example.com/~user@host/repo.git"
    assert _strip_credentials(url) == url


def test_strip_credentials_removes_userinfo_containing_a_slash():
    """A "/" inside the credential must not truncate the userinfo search
    window: real tokens (base64/JWT-derived) commonly contain "/", and
    bounding the search by the first "/" hides the real "@" and lets the
    whole unredacted credential pass through."""
    cases = {
        "https://user:pa/ss@github.com/org/repo.git": "https://github.com/org/repo.git",
        "https://x-access-token:gh_p/xyz@github.com/foo/bar.git": "https://github.com/foo/bar.git",
        "https://token/with/slashes@github.com/org/repo.git": "https://github.com/org/repo.git",
    }
    for leaky, expected in cases.items():
        stripped = _strip_credentials(leaky)
        assert stripped == expected
        assert "@" not in stripped
        assert "pa" not in stripped and "gh_p" not in stripped
        assert "token" not in stripped and "slashes" not in stripped
