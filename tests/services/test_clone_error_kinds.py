"""Tests for the typed CloneError taxonomy emitted by run_git_clone."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from quodeq.services._fs_clone import CloneError, run_git_clone
from quodeq.shared.git_errors import GitFailureKind


@pytest.fixture(autouse=True)
def _public_remote(monkeypatch):
    """The fake remote resolves to one public address, so the pin step
    never touches DNS and never refuses the clone."""
    monkeypatch.setattr("quodeq.services._fs_clone.resolve_addresses", lambda hostname: ("140.82.121.3",))


def _stderr(text: str) -> subprocess.CalledProcessError:
    err = subprocess.CalledProcessError(returncode=128, cmd=["git", "clone"])
    err.stderr = text.encode() if isinstance(text, str) else text
    return err


@pytest.mark.parametrize(
    "stderr_text,expected_kind",
    [
        ("Permission denied (publickey).", GitFailureKind.AUTH_REQUIRED),
        ("Authentication failed for 'https://...'", GitFailureKind.AUTH_REQUIRED),
        ("could not read Username for 'https://...'", GitFailureKind.AUTH_REQUIRED),
        ("Host key verification failed.", GitFailureKind.HOST_KEY),
        ("Could not resolve host: github.com", GitFailureKind.NETWORK),
        ("Connection timed out", GitFailureKind.NETWORK),
        ("Repository not found.", GitFailureKind.NOT_FOUND),
        ("fatal: repository 'https://example.com/x.git' not found", GitFailureKind.NOT_FOUND),
        ("destination path 'foo' already exists and is not an empty directory.", GitFailureKind.DEST_EXISTS),
        ("No space left on device", GitFailureKind.DISK),
        ("some unrelated git error", GitFailureKind.UNKNOWN),
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
        assert exc.value.kind == GitFailureKind.AUTH_REQUIRED


def test_run_git_clone_handles_none_stderr(tmp_path):
    """When stderr is None (e.g. capture_output disabled), classifies as unknown."""
    err = subprocess.CalledProcessError(returncode=128, cmd=["git", "clone"])
    err.stderr = None
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=err):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == GitFailureKind.UNKNOWN


def test_run_git_clone_timeout_classified_as_timeout(tmp_path):
    timeout = subprocess.TimeoutExpired(cmd=["git", "clone"], timeout=300)
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=timeout):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == GitFailureKind.TIMEOUT


def test_run_git_clone_missing_git_binary_classified_as_unknown(tmp_path):
    """FileNotFoundError (git not in PATH) is NOT a disk error."""
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=FileNotFoundError("git not found")):
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
        assert exc.value.kind == GitFailureKind.GIT_MISSING


def test_timeout_is_its_own_kind(tmp_path):
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=1)
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest", shallow_months=0)
    assert exc.value.kind is GitFailureKind.TIMEOUT
    assert exc.value.retryable is False


def test_env_reaches_the_clone_subprocess(tmp_path):
    with patch("quodeq.services._fs_clone.clone_repo") as clone_mock:
        run_git_clone("https://x/y.git", tmp_path / "dest", shallow_months=0, env={"GIT_CONFIG_COUNT": "1"})
    assert clone_mock.call_args.kwargs["env"] == {"GIT_CONFIG_COUNT": "1"}
