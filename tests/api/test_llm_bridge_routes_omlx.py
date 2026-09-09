"""Tests for the OMLX and provider-key llm_bridge API routes."""
from __future__ import annotations

from unittest.mock import patch

import pytest

_TEST_API_KEY = "sk-test"


@pytest.fixture()
def client(tmp_path):
    from quodeq.api.app import create_app
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# SEC-13 — the OMLX models route takes the API key from the X-Api-Key header,
#          never from the query string (query params leak via access logs,
#          browser history, and referrers).
# ---------------------------------------------------------------------------

class TestOmlxModels:
    def test_api_key_read_from_header(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_omlx_models") as mock:
            mock.return_value = []
            resp = client.get(
                "/api/omlx/models?base_url=http://localhost:10240",
                headers={"X-Api-Key": " sk-header "},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(base_url="http://localhost:10240", api_key="sk-header")

    def test_api_key_query_param_no_longer_honored(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_omlx_models") as mock:
            mock.return_value = []
            resp = client.get("/api/omlx/models?api_key=sk-leaky")
        assert resp.status_code == 200
        mock.assert_called_once_with(base_url=None, api_key=None)


# ---------------------------------------------------------------------------
# REL-084/085/086/087/088 — POST routes must 400 on a JSON body that parses
# but is not an object (e.g. [1] or "x"), instead of crashing at data.get.
# ---------------------------------------------------------------------------

class TestJsonObjectBodyRequired:
    @pytest.mark.parametrize("route", [
        "/api/ollama/test-concurrency",
        "/api/ollama/estimate-agents",
        "/api/llamacpp/test-concurrency",
        "/api/omlx/test-concurrency",
        "/api/provider/test",
    ])
    def test_array_body_returns_400(self, client, route):
        resp = client.post(route, json=[1], headers={"Origin": "http://localhost"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    @pytest.mark.parametrize("route", [
        "/api/ollama/test-concurrency",
        "/api/llamacpp/test-concurrency",
        "/api/omlx/test-concurrency",
    ])
    def test_string_body_returns_400(self, client, route):
        resp = client.post(route, json="x", headers={"Origin": "http://localhost"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_omlx_non_string_base_url_returns_400(self, client):
        resp = client.post(
            "/api/omlx/test-concurrency",
            json={"model": "m", "base_url": 123},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_omlx_non_string_api_key_returns_400(self, client):
        resp = client.post(
            "/api/omlx/test-concurrency",
            json={"model": "m", "api_key": ["k"]},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_omlx_valid_string_fields_pass_through(self, client):
        with patch("quodeq.api.llm_bridge_routes.run_omlx_concurrency_test") as mock:
            mock.return_value = {"recommended": 2}
            resp = client.post(
                "/api/omlx/test-concurrency",
                json={"model": "m", "base_url": " http://x ", "api_key": ""},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("m", base_url="http://x", api_key=None)


# ---------------------------------------------------------------------------
# base_url on the omlx routes must pass the same SSRF validation as
# /api/provider/test: http(s) scheme only (private/LAN hosts stay allowed
# for self-hosted servers).
# ---------------------------------------------------------------------------

class TestOmlxBaseUrlValidation:
    def _get(self, client, route, base_url):
        return client.get(f"{route}?base_url={base_url}")

    @pytest.mark.parametrize("route", ["/api/omlx/status", "/api/omlx/models"])
    def test_non_http_scheme_rejected(self, client, route):
        resp = self._get(client, route, "ftp://internal-host/models")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_URL"

    @pytest.mark.parametrize("route", ["/api/omlx/status", "/api/omlx/models"])
    def test_missing_hostname_rejected(self, client, route):
        resp = self._get(client, route, "http://")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_URL"

    def test_post_route_rejects_non_http_scheme(self, client):
        resp = client.post(
            "/api/omlx/test-concurrency",
            json={"model": "m", "base_url": "file:///etc/passwd"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_URL"

    def test_localhost_base_url_accepted(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_omlx_status") as mock:
            mock.return_value = {"running": True}
            resp = self._get(client, "/api/omlx/status", "http://127.0.0.1:10240")
        assert resp.status_code == 200
        mock.assert_called_once_with(base_url="http://127.0.0.1:10240")


# ---------------------------------------------------------------------------
# Task 2 — backend secure storage for provider API keys.
# ---------------------------------------------------------------------------

class TestProviderKeyRoutes:
    def test_store_reports_stored_and_secure(self, client):
        with patch("quodeq.api.llm_bridge_routes._store_api_key") as mock:
            mock.return_value = (True, True)
            resp = client.post(
                "/api/provider/key",
                json={"provider": "claude", "apiKey": _TEST_API_KEY},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200
        assert resp.get_json() == {"stored": True, "secure": True}
        mock.assert_called_once_with("claude", _TEST_API_KEY)

    def test_store_reports_cleartext_fallback_used(self, client):
        with patch("quodeq.api.llm_bridge_routes._store_api_key") as mock:
            mock.return_value = (True, False)
            resp = client.post(
                "/api/provider/key",
                json={"provider": "claude", "apiKey": _TEST_API_KEY},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200
        assert resp.get_json() == {"stored": True, "secure": False}

    def test_store_missing_provider_returns_400(self, client):
        resp = client.post(
            "/api/provider/key",
            json={"apiKey": _TEST_API_KEY},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"

    def test_store_missing_api_key_returns_400(self, client):
        resp = client.post(
            "/api/provider/key",
            json={"provider": "claude"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"

    def test_store_non_object_body_returns_400(self, client):
        resp = client.post("/api/provider/key", json=[1], headers={"Origin": "http://localhost"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_key_status_never_echoes_raw_key(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_api_key_secure") as mock:
            mock.return_value = "sk-should-never-appear-in-response"
            resp = client.get("/api/provider/key-status?provider=claude")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"configured": True}
        assert "sk-should-never-appear-in-response" not in resp.get_data(as_text=True)

    def test_key_status_missing_provider_returns_400(self, client):
        resp = client.get("/api/provider/key-status")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"

    def test_key_status_not_configured(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_api_key_secure") as mock:
            mock.return_value = None
            resp = client.get("/api/provider/key-status?provider=claude")
        assert resp.status_code == 200
        assert resp.get_json() == {"configured": False}

    def test_store_then_status_round_trip_via_cleartext_fallback(self, client, tmp_path, monkeypatch):
        """End-to-end round trip, forcing the keyring-failure fallback so the
        real cleartext path (not just a mock) gets exercised."""
        import keyring.errors

        from quodeq.config import ai_provider
        from quodeq.config.paths import ConfigPaths

        cfg_paths = ConfigPaths.from_root(tmp_path)
        monkeypatch.setattr(ai_provider, "default_paths", lambda: cfg_paths)

        def raise_keyring_error(*args, **kwargs):
            raise keyring.errors.KeyringError("no backend available")

        monkeypatch.setattr(ai_provider.keyring, "set_password", raise_keyring_error)
        monkeypatch.setattr(ai_provider.keyring, "get_password", raise_keyring_error)

        store_resp = client.post(
            "/api/provider/key",
            json={"provider": "gemini", "apiKey": "sk-roundtrip"},
            headers={"Origin": "http://localhost"},
        )
        assert store_resp.status_code == 200
        assert store_resp.get_json() == {"stored": True, "secure": False}

        status_resp = client.get("/api/provider/key-status?provider=gemini")
        assert status_resp.status_code == 200
        assert status_resp.get_json() == {"configured": True}

        # The raw key must never leak back through key-status.
        assert "sk-roundtrip" not in status_resp.get_data(as_text=True)

    def test_provider_name_with_newline_is_rejected_before_the_env_file(
        self, client, tmp_path, monkeypatch,
    ):
        """Regression: the provider name is interpolated into `export …` lines
        in .quodeq.env, which _env_loader loads into os.environ. A newline in
        it injected arbitrary env vars into the running process."""
        import keyring.errors

        from quodeq.config import ai_provider
        from quodeq.config.paths import ConfigPaths

        cfg_paths = ConfigPaths.from_root(tmp_path)
        monkeypatch.setattr(ai_provider, "default_paths", lambda: cfg_paths)
        monkeypatch.setattr(
            ai_provider.keyring, "set_password",
            lambda *a: (_ for _ in ()).throw(keyring.errors.KeyringError("no backend")),
        )

        resp = client.post(
            "/api/provider/key",
            json={"provider": "gemini\nexport EVIL=pwned", "apiKey": "sk-x"},
            headers={"Origin": "http://localhost"},
        )

        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"
        assert not cfg_paths.env_file.exists()
