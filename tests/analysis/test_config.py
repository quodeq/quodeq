import importlib


def test_invalid_max_turns_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "not-a-number")
    import quodeq.analysis._config as config_mod
    importlib.reload(config_mod)
    try:
        assert config_mod._DEFAULT_MAX_TURNS == 200
    finally:
        monkeypatch.delenv("QUODEQ_DEFAULT_MAX_TURNS", raising=False)
        importlib.reload(config_mod)  # restore real env for subsequent tests
