"""Adversarial remote URLs whose credential itself contains a "/".

Real tokens (base64/JWT-derived, CI PATs) commonly contain "/", so bounding
the userinfo search by the FIRST "/" hides the real "@" and lets the whole
unredacted credential through. Both readers of a credentialed URL are held
to these cases -- the API's masking ``_sanitize_url`` and registration's
stripping ``_strip_credentials`` -- each against its own expected output,
which is why the cases live here rather than in one of the two test modules.

Each entry is ``(url, tail)``: *tail* is everything after the userinfo "@",
so masking expects ``https://***@<tail>`` and stripping ``https://<tail>``.
"""
from __future__ import annotations

SLASH_IN_CREDENTIAL_URLS = (
    ("https://user:pa/ss@github.com/org/repo.git", "github.com/org/repo.git"),
    ("https://x-access-token:gh_p/xyz@github.com/foo/bar.git", "github.com/foo/bar.git"),
    ("https://token/with/slashes@github.com/org/repo.git", "github.com/org/repo.git"),
)

# The credential fragments that must never survive either treatment.
SLASH_CREDENTIAL_SECRETS = ("pa/ss", "gh_p/xyz", "token/with/slashes")
