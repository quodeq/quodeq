from quodeq.action_api import create_app


def test_action_api_health():
    """Integration test: exercises the full Flask app to verify /api/health."""
    app = create_app()
    client = app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert "version" in data
