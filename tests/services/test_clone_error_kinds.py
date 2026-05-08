"""Tests for the typed CloneError taxonomy emitted by run_git_clone."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from quodeq.services._fs_clone import CloneError, run_git_clone


def _stderr(text: str) -> subprocess.CalledProcessError:
    err = subprocess.CalledProcessError(returncode=128, cmd=["git", "clone"])
    err.stderr = text.encode() if isinstance(text, str) else text
    return err


@pytest.mark.parametrize(
    "stderr_text,expected_kind",
    [
        ("Permission denied (publickey).", "auth"),
        ("Authentication failed for 'https://...'", "auth"),
        ("could not read Username for 'https://...'", "auth"),
        ("Could not resolve host: github.com", "network"),
        ("Connection timed out", "network"),
        ("Repository not found.", "repo_not_found"),
        ("fatal: repository 'https://example.com/x.git' not found", "repo_not_found"),
        ("destination path 'foo' already exists and is not an empty directory.", "dest_exists"),
        ("No space left on device", "disk"),
        ("some unrelated git error", "unknown"),
    ],
)
def test_classify_stderr(stderr_text, expected_kind, tmp_path):
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.side_effect = _stderr(stderr_text)
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == expected_kind


def test_run_git_clone_success_returns_none(tmp_path):
    """Successful clone returns None (no exception). Existing callers that
    treated truthy return value as success need to flip to try/except."""
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.return_value = None  # success has no return value used
        result = run_git_clone("https://x/y.git", tmp_path / "dest")
        assert result is None


def test_run_git_clone_handles_already_decoded_stderr(tmp_path):
    """When subprocess returns stderr as str (text mode), decoding still works."""
    err = subprocess.CalledProcessError(returncode=128, cmd=["git", "clone"])
    err.stderr = "Authentication failed for 'https://...'"  # str, not bytes
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=err):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == "auth"


def test_run_git_clone_handles_none_stderr(tmp_path):
    """When stderr is None (e.g. capture_output disabled), classifies as unknown."""
    err = subprocess.CalledProcessError(returncode=128, cmd=["git", "clone"])
    err.stderr = None
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=err):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == "unknown"


def test_run_git_clone_timeout_classified_as_network(tmp_path):
    timeout = subprocess.TimeoutExpired(cmd=["git", "clone"], timeout=300)
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=timeout):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == "network"


def test_run_git_clone_missing_git_binary_classified_as_unknown(tmp_path):
    """FileNotFoundError (git not in PATH) is NOT a disk error."""
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=FileNotFoundError("git not found")):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == "unknown"
