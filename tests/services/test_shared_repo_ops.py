"""SharedRepoOps seam: injected fakes back connect_shared_repo/disconnect_shared_repo,
and the existing module-level patches keep biting when no ops are injected."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.services.shared_connect import ConnectStatus, connect_shared_repo
from quodeq.services.shared_repo import RepoFormat, disconnect_shared_repo
from quodeq.services.shared_repo_ops import SharedRepoOps
from quodeq.services.shared_settings import SharedSettings


def test_connect_uses_injected_ops():
    """Every SharedRepoOps field is a fake; assert each one was actually called."""
    calls = {}

    def fake_validate(url):
        calls["validate"] = url

    def fake_read_state(url):
        calls["read_state"] = url
        return RepoFormat.MISSING

    def fake_ensure_clone(url):
        calls["ensure_clone"] = url
        return "fake-repo-handle"

    def fake_check_format(repo):
        calls["check_format"] = repo
        return RepoFormat.OK

    def fake_write_settings(settings, *, log=None):
        calls["write_settings"] = settings

    ops = SharedRepoOps(
        validate=fake_validate,
        read_state=fake_read_state,
        ensure_clone=fake_ensure_clone,
        check_format=fake_check_format,
        write_settings=fake_write_settings,
    )

    with patch("quodeq.services.shared_connect.validate_remote_url", side_effect=AssertionError("must not call the real validate_remote_url")):
        outcome = connect_shared_repo("https://example.com/repo.git", ops=ops)

    assert outcome.status == RepoFormat.OK
    assert calls["validate"] == "https://example.com/repo.git"
    assert calls["read_state"] == "https://example.com/repo.git"
    assert calls["ensure_clone"] == "https://example.com/repo.git"
    assert calls["check_format"] == "fake-repo-handle"
    assert calls["write_settings"] == SharedSettings(url="https://example.com/repo.git")


def test_connect_invalid_url_never_reaches_clone():
    calls = {"ensure_clone": 0}

    def fake_validate(url):
        raise ValueError("bad url")

    def fake_ensure_clone(url):
        calls["ensure_clone"] += 1
        return None

    ops = SharedRepoOps(validate=fake_validate, ensure_clone=fake_ensure_clone)
    outcome = connect_shared_repo("file:///nope", ops=ops)

    assert outcome.status == ConnectStatus.INVALID_URL
    assert calls["ensure_clone"] == 0


def test_connect_default_ops_still_resolve_to_the_patched_module_globals():
    """Existing patch targets keep biting: no ops injected -> falls back to
    shared_connect's own validate_remote_url/ensure_shared_clone globals."""
    with patch("quodeq.services.shared_connect.validate_remote_url", lambda url: None), \
         patch("quodeq.services.shared_connect.ensure_shared_clone", lambda url: None):
        outcome = connect_shared_repo("https://example.com/repo.git")

    assert outcome.status == ConnectStatus.CLONE_FAILED


def test_disconnect_uses_injected_ops():
    calls = {}

    def fake_read_settings():
        return SharedSettings(url="https://example.com/repo.git")

    def fake_write_settings(settings, *, log=None):
        calls["write_settings"] = settings

    class _FakeLock:
        def __enter__(self):
            calls["lock_entered"] = True
            return self

        def __exit__(self, *exc):
            calls["lock_exited"] = True
            return False

    def fake_clone_lock(url):
        calls["clone_lock"] = url
        return _FakeLock()

    def fake_remove_clone_dir(path):
        calls["remove_clone_dir"] = path

    def fake_shared_cache_dir(url):
        calls["shared_cache_dir"] = url
        return f"/cache/{url}"

    ops = SharedRepoOps(
        read_settings=fake_read_settings,
        write_settings=fake_write_settings,
        clone_lock=fake_clone_lock,
        remove_clone_dir=fake_remove_clone_dir,
        shared_cache_dir=fake_shared_cache_dir,
    )

    with patch("quodeq.services.shared_repo.remove_clone_dir", side_effect=AssertionError("must not call the real remove_clone_dir")):
        disconnect_shared_repo(ops=ops)

    assert calls["write_settings"] == SharedSettings(url=None)
    assert calls["clone_lock"] == "https://example.com/repo.git"
    assert calls["shared_cache_dir"] == "https://example.com/repo.git"
    assert calls["remove_clone_dir"] == "/cache/https://example.com/repo.git"
    assert calls["lock_entered"] and calls["lock_exited"]


def test_disconnect_default_ops_still_resolve_to_the_patched_remove_clone_dir(tmp_path, monkeypatch):
    """Existing patch target keeps biting: no ops injected -> falls back to
    shared_repo's own remove_clone_dir global, resolved at call time."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    from quodeq.services.shared_settings import write_settings as real_write_settings
    real_write_settings(SharedSettings(url="https://example.com/repo.git"))

    with patch("quodeq.services.shared_repo.remove_clone_dir") as mock_remove:
        disconnect_shared_repo()

    mock_remove.assert_called_once()
