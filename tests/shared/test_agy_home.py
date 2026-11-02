"""The dedicated agy home: keychain link, MCP registration env, scan env."""
import pytest

from quodeq.analysis.subprocess import build_analysis_env
from quodeq.shared.agy_home import dedicated_agy_home, mcp_register_overrides


@pytest.fixture()
def user_home(tmp_path, monkeypatch):
    home = tmp_path / "user"
    (home / "Library" / "Keychains").mkdir(parents=True)
    monkeypatch.delenv("QUODEQ_DIR", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    return home


def test_dedicated_home_links_only_the_users_keychains(user_home):
    home = dedicated_agy_home({"HOME": str(user_home)})
    assert home == user_home / ".quodeq" / "agy"
    assert (home / "Library" / "Keychains").resolve() == (user_home / "Library" / "Keychains").resolve()
    assert not (home / ".gemini").exists()  # none of the user's agy config comes along


def test_scans_run_agy_with_the_dedicated_home(user_home):
    env = build_analysis_env("agy", env={"HOME": str(user_home), "PATH": "/bin"})
    assert env["HOME"] == str(user_home / ".quodeq" / "agy")


def test_agy_registration_lands_in_the_dedicated_home_and_server_keeps_users_home(user_home):
    env, flags = mcp_register_overrides("agy", {"HOME": str(user_home)})
    assert env["HOME"] == str(user_home / ".quodeq" / "agy")
    assert flags == ["-e", f"HOME={user_home}"]


def test_other_clis_register_as_before(user_home):
    assert mcp_register_overrides("gemini", {"HOME": str(user_home)}) == (None, [])
