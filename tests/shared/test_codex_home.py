"""The dedicated Codex home links the user's login instead of copying it."""
from pathlib import Path

from quodeq.shared import codex_home


def _env(tmp_path):
    user = tmp_path / "user-codex"
    user.mkdir()
    (user / "auth.json").write_text('{"tokens": "live"}')
    return {"CODEX_HOME": str(user), "QUODEQ_DIR": str(tmp_path / "state")}


def test_login_is_a_link_to_the_users_auth(tmp_path):
    # Refresh tokens are single-use: a copy refreshing on its own logs the
    # user's Codex out. One file, written through the link, avoids that.
    env = _env(tmp_path)
    auth = codex_home.dedicated_codex_home(env) / "auth.json"
    assert auth.is_symlink()
    assert auth.resolve() == (tmp_path / "user-codex" / "auth.json").resolve()


def test_an_earlier_copy_is_replaced_by_the_link(tmp_path):
    env = _env(tmp_path)
    home = codex_home.dedicated_codex_home_path(env)
    home.mkdir(parents=True)
    (home / "auth.json").write_text('{"tokens": "stale copy"}')
    codex_home.dedicated_codex_home(env)
    assert (home / "auth.json").is_symlink()


def test_falls_back_to_a_copy_where_links_are_unavailable(tmp_path, monkeypatch):
    def no_links(self, target):
        raise OSError("symlinks need a privilege here")

    monkeypatch.setattr(Path, "symlink_to", no_links)
    env = _env(tmp_path)
    auth = codex_home.dedicated_codex_home(env) / "auth.json"
    assert not auth.is_symlink()
    assert auth.read_text() == '{"tokens": "live"}'


def test_user_auth_file_is_none_without_a_login(tmp_path):
    assert codex_home.user_codex_auth_file({"CODEX_HOME": str(tmp_path)}) is None
