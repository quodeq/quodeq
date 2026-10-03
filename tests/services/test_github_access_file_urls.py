import subprocess

from quodeq.services.github_access import AccessCache, AccessDeps, AccessMethod, resolve_access
from quodeq.shared.git_errors import GitFailureKind


def _boom(*_args, **_kwargs):
    raise AssertionError("a local repository must never be probed")


def test_a_local_repo_is_reachable_without_any_probe(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True, timeout=30)
    url = (origin).as_uri()
    deps = AccessDeps(probe=_boom, pin=_boom, load_account=_boom, gh=_boom)
    result = resolve_access(url, deps=deps, cache=AccessCache())
    assert result.reachable is True
    assert result.method is AccessMethod.LOCAL
    assert result.kind is GitFailureKind.OK
    assert result.env is None
    assert result.clone_url == url
    assert result.host == ""
    assert result.is_github is False


def test_a_plain_folder_is_rejected_as_not_a_git_repo(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "plain").mkdir()
    result = resolve_access((tmp_path / 'plain').as_uri(), deps=AccessDeps(probe=_boom, pin=_boom), cache=AccessCache())
    assert result.reachable is False
    assert result.kind is GitFailureKind.NOT_A_GIT_REPO
