"""Tests for the shared-repo settings store."""
from quodeq.services.shared_settings import (
    SharedSettings,
    read_settings,
    shared_settings_path,
    write_settings,
)


def test_read_settings_missing_file_returns_empty(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    settings = read_settings(env=env)
    assert settings.url is None


def test_write_then_read_round_trip(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    write_settings(SharedSettings(url="git@github.com:team/results.git"), env=env)
    assert read_settings(env=env).url == "git@github.com:team/results.git"
    assert shared_settings_path(env=env) == tmp_path / "shared.json"


def test_read_settings_corrupt_file_returns_empty(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    (tmp_path / "shared.json").write_text("{not json", encoding="utf-8")
    assert read_settings(env=env).url is None
