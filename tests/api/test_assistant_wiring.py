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
