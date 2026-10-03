from pathlib import Path

from quodeq.config.clone_env import default_clone_root


def test_repos_dir_env_wins():
    assert default_clone_root({"QUODEQ_REPOS_DIR": "/data/repos"}) == Path("/data/repos")


def test_unset_or_blank_falls_back_to_home():
    expected = Path.home() / "quodeq" / "repos"
    assert default_clone_root({}) == expected
    assert default_clone_root({"QUODEQ_REPOS_DIR": "  "}) == expected
