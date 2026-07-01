from pathlib import Path

from quodeq.shared._env import get_score_cache_path, score_cache_disabled


def test_explicit_env_path_wins():
    env = {"QUODEQ_SCORE_CACHE_PATH": "/tmp/x/score.db"}
    assert get_score_cache_path(env=env) == "/tmp/x/score.db"


def test_derives_from_index_db_dir():
    env = {"QUODEQ_INDEX_DB_PATH": "/tmp/quodeqtest/index.db"}
    assert get_score_cache_path(env=env) == str(Path("/tmp/quodeqtest") / "score_cache.db")


def test_kill_switch():
    assert score_cache_disabled(env={"QUODEQ_DISABLE_SCORE_CACHE": "1"}) is True
    assert score_cache_disabled(env={"QUODEQ_DISABLE_SCORE_CACHE": "true"}) is True
    assert score_cache_disabled(env={}) is False
