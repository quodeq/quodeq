"""classify_git_output: one classifier for every git failure quodeq surfaces."""
from __future__ import annotations

import pytest

from quodeq.shared.git_errors import GitFailureKind, SIGN_IN_KINDS, classify_git_output, output_tail


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Permission denied (publickey).", GitFailureKind.AUTH_REQUIRED),
        ("fatal: Authentication failed for 'https://github.com/o/r.git/'", GitFailureKind.AUTH_REQUIRED),
        ("fatal: could not read Username for 'https://github.com': terminal prompts disabled", GitFailureKind.AUTH_REQUIRED),
        ("fatal: could not read Password for 'https://x@github.com': terminal prompts disabled", GitFailureKind.AUTH_REQUIRED),
        ("remote: Invalid username or token. Password authentication is not supported", GitFailureKind.AUTH_REQUIRED),
        # GitHub answers a private repo without access as not-found, not as auth.
        ("remote: Repository not found.\nfatal: repository 'https://github.com/o/r.git/' not found", GitFailureKind.NOT_FOUND),
        ("fatal: 'o/r' does not appear to be a git repository", GitFailureKind.NOT_FOUND),
        # Host key is its own class: sign-in cannot help here.
        ("Host key verification failed.\nfatal: Could not read from remote repository.", GitFailureKind.HOST_KEY),
        ("fatal: unable to access 'https://x/': Could not resolve host: github.com", GitFailureKind.NETWORK),
        ("ssh: connect to host github.com port 22: Connection timed out", GitFailureKind.NETWORK),
        ("ssh: connect to host github.com port 22: Connection refused", GitFailureKind.NETWORK),
        ("fatal: unable to access 'https://x/': Failed to connect to github.com port 443", GitFailureKind.NETWORK),
        ("fatal: destination path 'r' already exists and is not an empty directory.", GitFailureKind.DEST_EXISTS),
        ("error: No space left on device", GitFailureKind.DISK),
        ("some unrelated git error", GitFailureKind.UNKNOWN),
        ("", GitFailureKind.UNKNOWN),
    ],
)
def test_classify(text, expected):
    assert classify_git_output(text) is expected


def test_host_key_wins_over_permission_denied():
    # Both markers can appear in one ssh failure; host key is the actionable one.
    text = "Host key verification failed.\nPermission denied (publickey)."
    assert classify_git_output(text) is GitFailureKind.HOST_KEY


def test_sign_in_kinds_are_exactly_auth_and_not_found():
    assert SIGN_IN_KINDS == frozenset({GitFailureKind.AUTH_REQUIRED, GitFailureKind.NOT_FOUND})


def test_output_tail_keeps_the_last_lines_and_strips():
    text = "\n".join(f"line {i}" for i in range(200)) + "\n"
    tail = output_tail(text, limit=40)
    assert len(tail) <= 40
    assert tail.endswith("line 199")
    assert output_tail("  x  ") == "x"
    assert output_tail(None) == ""
