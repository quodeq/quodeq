"""Tests for shallow cloning in run_git_clone and its full-clone fallback.

Online (URL) repos are cloned with a bounded history window: enough for the
git churn scoring lookback (git_lookback_months, default 3), a fraction of
the download of a full clone. Servers or repos that cannot satisfy a shallow
request fall back to a full clone; deterministic failures (auth, not found)
do not retry.
"""

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
    err.stderr = text.encode()
    return err


def _has_shallow_args(cmd: list[str]) -> bool:
    return (
        "--single-branch" in cmd
        and "--no-tags" in cmd
        and any(a.startswith("--shallow-since=") for a in cmd)
    )


def test_clone_is_shallow_by_default(tmp_path):
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.return_value = None
        run_git_clone("https://x/y.git", tmp_path / "dest")
    assert run_mock.call_count == 1
    assert _has_shallow_args(run_mock.call_args[0][0])


def test_shallow_failure_falls_back_to_full_clone(tmp_path):
    """A shallow request the server/repo cannot satisfy retries as a full clone."""
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.side_effect = [_stderr("fatal: error processing shallow info: 4"), None]
        run_git_clone("https://x/y.git", tmp_path / "dest")
    assert run_mock.call_count == 2
    assert not _has_shallow_args(run_mock.call_args_list[1][0][0])


def test_fallback_removes_partial_clone_dir(tmp_path):
    """A failed shallow attempt may leave a partial dest; the retry must not
    trip over it with a dest_exists error."""
    dest = tmp_path / "dest"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            dest.mkdir()
            raise _stderr("some unrelated git error")
        assert not dest.exists(), "partial clone dir must be removed before the retry"

    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=fake_run):
        run_git_clone("https://x/y.git", dest)
    assert len(calls) == 2


def test_fallback_removes_partial_clone_with_readonly_objects(
    tmp_path, windows_unlink_semantics
):
    """A partial dest holds read-only git object files, which Windows
    refuses to unlink. rmtree(ignore_errors=True) silently left them
    behind, turning the retry into a bogus dest_exists failure. Cleanup
    must clear the read-only bit and retry (shared_repo.remove_clone_dir)."""
    dest = tmp_path / "dest"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            objects = dest / ".git" / "objects" / "09"
            objects.mkdir(parents=True)
            blob = objects / "deadbeef"
            blob.write_bytes(b"x")
            blob.chmod(0o444)
            raise _stderr("some unrelated git error")
        assert not dest.exists(), "partial clone dir must be removed before the retry"

    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=fake_run):
        run_git_clone("https://x/y.git", dest)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "stderr_text,expected_kind",
    [
        ("Permission denied (publickey).", GitFailureKind.AUTH_REQUIRED),
        ("Repository not found.", GitFailureKind.NOT_FOUND),
        ("destination path 'foo' already exists and is not an empty directory.", "dest_exists"),
        ("No space left on device", "disk"),
    ],
)
def test_deterministic_failures_do_not_retry(stderr_text, expected_kind, tmp_path):
    """Failures a full clone would hit identically raise once, without a retry."""
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.side_effect = _stderr(stderr_text)
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
    assert exc.value.kind == expected_kind
    assert run_mock.call_count == 1


def test_timeout_does_not_retry(tmp_path):
    """A shallow clone that already spent the whole timeout must not start a
    second, slower full clone."""
    timeout = subprocess.TimeoutExpired(cmd=["git", "clone"], timeout=300)
    with patch("quodeq.services._fs_clone._subprocess.run", side_effect=timeout) as run_mock:
        with pytest.raises(CloneError) as exc:
            run_git_clone("https://x/y.git", tmp_path / "dest")
    assert exc.value.kind == GitFailureKind.TIMEOUT
    assert run_mock.call_count == 1


def test_env_zero_disables_shallow(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CLONE_SHALLOW_MONTHS", "0")
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.return_value = None
        run_git_clone("https://x/y.git", tmp_path / "dest")
    assert run_mock.call_count == 1
    assert not _has_shallow_args(run_mock.call_args[0][0])


def test_env_overrides_shallow_window(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CLONE_SHALLOW_MONTHS", "12")
    with patch("quodeq.services._fs_clone._subprocess.run") as run_mock:
        run_mock.return_value = None
        run_git_clone("https://x/y.git", tmp_path / "dest")
    cmd = run_mock.call_args[0][0]
    assert "--shallow-since=12 months ago" in cmd


# --- address pinning: git connects to the addresses the URL check saw ---


def _argv_with(resolved, url: str, tmp_path) -> list[str]:
    with patch("quodeq.services._fs_clone.resolve_addresses", return_value=resolved), \
         patch("quodeq.data.fs.repo_clone.subprocess.run") as run_mock:
        run_git_clone(url, tmp_path / "dest", shallow_months=0)
    run_mock.assert_called_once()
    return run_mock.call_args[0][0]


def test_https_clone_pins_every_resolved_address_before_the_subcommand(tmp_path) -> None:
    argv = _argv_with(("140.82.121.3", "2606:50c0:8000::153"), "https://github.com/acme/repo.git", tmp_path)

    assert argv[:3] == ["git", "-c", "http.curloptResolve=github.com:443:140.82.121.3,2606:50c0:8000::153"]
    assert argv[3] == "clone"


def test_pin_uses_the_port_in_the_url(tmp_path) -> None:
    argv = _argv_with(("140.82.121.3",), "http://git.example:8080/acme/repo.git", tmp_path)

    assert argv[2] == "http.curloptResolve=git.example:8080:140.82.121.3"


def test_scp_form_remote_is_not_pinned(tmp_path) -> None:
    with patch("quodeq.services._fs_clone.resolve_addresses") as resolve, \
         patch("quodeq.data.fs.repo_clone.subprocess.run") as run_mock:
        run_git_clone("git@github.com:acme/repo.git", tmp_path / "dest", shallow_months=0)

    resolve.assert_not_called()
    assert run_mock.call_args[0][0][:2] == ["git", "clone"]


@pytest.mark.parametrize("resolved", [("10.0.0.7",), ("140.82.121.3", "127.0.0.1"), ("169.254.169.254",)])
def test_a_rebinding_answer_refuses_the_clone_before_git_runs(tmp_path, resolved) -> None:
    with patch("quodeq.services._fs_clone.resolve_addresses", return_value=resolved), \
         patch("quodeq.data.fs.repo_clone.subprocess.run") as run_mock, \
         pytest.raises(CloneError, match="private/internal"):
        run_git_clone("https://github.com/acme/repo.git", tmp_path / "dest", shallow_months=0)

    run_mock.assert_not_called()


def test_an_unresolvable_host_refuses_the_clone(tmp_path) -> None:
    with patch("quodeq.services._fs_clone.resolve_addresses", return_value=()), \
         patch("quodeq.data.fs.repo_clone.subprocess.run") as run_mock, \
         pytest.raises(CloneError, match="could not resolve"):
        run_git_clone("https://github.com/acme/repo.git", tmp_path / "dest", shallow_months=0)

    run_mock.assert_not_called()
