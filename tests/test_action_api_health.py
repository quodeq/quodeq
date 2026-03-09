from quodeq.action_api import create_app


def test_action_api_health():
    app = create_app()
    client = app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
