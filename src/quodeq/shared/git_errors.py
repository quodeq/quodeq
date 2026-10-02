"""The one classifier for git subprocess failures.

Used by the access probe (data/fs/git_access_probe.py), the onboarding clone
(services/_fs_clone.py) and the shared-repo runner (data/fs/shared_repo.py),
so every clone and probe in the app agrees on what a given git output means.
Pure string logic: importable from the core-only ``shared`` layer.
"""
from __future__ import annotations

from enum import StrEnum


class GitFailureKind(StrEnum):
    """Why a git remote operation failed, as the API reports it (wire values)."""

    OK = "ok"
    AUTH_REQUIRED = "auth_required"
    NOT_FOUND = "not_found"
    HOST_KEY = "host_key"
    NETWORK = "network"
    TIMEOUT = "timeout"
    DEST_EXISTS = "dest_exists"
    DISK = "disk"
    INVALID_URL = "invalid_url"
    GIT_MISSING = "git_missing"
    GIT_TOO_OLD = "git_too_old"
    UNKNOWN = "unknown"


# Kinds where signing in to GitHub can change the answer. GitHub reports a
# private repository the caller cannot see as "not found", so NOT_FOUND is in.
SIGN_IN_KINDS: frozenset[GitFailureKind] = frozenset({GitFailureKind.AUTH_REQUIRED, GitFailureKind.NOT_FOUND})

# Order matters: the first matching group wins. HOST_KEY is checked before
# AUTH because an ssh host-key failure is often followed by "Permission
# denied", and only the host-key line is actionable.
_HOST_KEY_MARKERS = ("Host key verification failed",)
_AUTH_MARKERS = (
    "Permission denied",
    "Authentication failed",
    "could not read Username",
    "could not read Password",
    "Invalid username or token",
    "HTTP Basic: Access denied",
)
_NOT_FOUND_MARKERS = (
    "Repository not found",
    "repository '",
    "' not found",
    "does not appear to be a git repository",
)
_DEST_EXISTS_MARKERS = ("already exists and is not an empty directory",)
_DISK_MARKERS = ("No space left on device", "disk full")
_NETWORK_MARKERS = (
    "Could not resolve host",
    "Connection timed out",
    "Connection refused",
    "Operation timed out",
    "Failed to connect to",
    "Could not connect to server",
)

_ORDERED = (
    (_HOST_KEY_MARKERS, GitFailureKind.HOST_KEY),
    (_AUTH_MARKERS, GitFailureKind.AUTH_REQUIRED),
    (_NOT_FOUND_MARKERS, GitFailureKind.NOT_FOUND),
    (_DEST_EXISTS_MARKERS, GitFailureKind.DEST_EXISTS),
    (_DISK_MARKERS, GitFailureKind.DISK),
    (_NETWORK_MARKERS, GitFailureKind.NETWORK),
)

_DEFAULT_TAIL = 500


def classify_git_output(text: str | None) -> GitFailureKind:
    """Map git's merged stdout+stderr to a :class:`GitFailureKind`."""
    s = text or ""
    for markers, kind in _ORDERED:
        if any(m in s for m in markers):
            return kind
    return GitFailureKind.UNKNOWN


def output_tail(text: str | None, limit: int = _DEFAULT_TAIL) -> str:
    """The last *limit* characters of *text*, stripped. Safe to show a user:
    callers only pass output of a git command that actually ran."""
    s = (text or "").strip()
    return s[-limit:] if len(s) > limit else s
