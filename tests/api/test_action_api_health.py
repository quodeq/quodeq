from quodeq.api.app import create_app


def test_action_api_health():
    """Integration test: exercises the full Flask app to verify /api/health."""
    app = create_app()
    client = app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert "version" in data
    # The state folder's identity: the UI keys the welcome's skip on it, so a
    # wiped folder shows the welcome again. Stable across calls.
    assert len(data["instanceId"]) == 32
    assert client.get("/api/health").get_json()["instanceId"] == data["instanceId"]
