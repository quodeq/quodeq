from quodeq.api.app import create_app


def test_assistant_routes_mounted(tmp_path):
    app = create_app(test_config={
        "TESTING": True,
        "ASSISTANT_DB_PATH": str(tmp_path / "assistant.db"),
    })
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/assistant/sessions" in rules
    assert "/api/assistant/sessions/<sid>/events" in rules
    assert "/api/assistant/actions/<action_id>/apply" in rules


def test_assistant_db_path_defaults(tmp_path):
    app = create_app(test_config={"TESTING": True})
    assert app.config["ASSISTANT_DB_PATH"].endswith("assistant.db")


def test_assistant_db_path_honors_quodeq_dir(tmp_path, monkeypatch):
    """QUODEQ_DIR must redirect the assistant DB default (env isolation).

    Regression: the default was hardcoded to ~/.quodeq/assistant.db, so
    env-isolated test/dev servers leaked assistant sessions into the
    developer's real store.
    """
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    app = create_app(test_config={"TESTING": True})
    assert app.config["ASSISTANT_DB_PATH"] == str(tmp_path / "assistant.db")


def test_assistant_db_path_falls_back_to_home(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_DIR", raising=False)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    app = create_app(test_config={"TESTING": True})
    assert app.config["ASSISTANT_DB_PATH"] == str(
        tmp_path / ".quodeq" / "assistant.db"
    )
