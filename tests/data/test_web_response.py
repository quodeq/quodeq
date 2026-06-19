"""Tests for data/web/_response.py — ServerError embeds the HTTP status (#472)."""
from __future__ import annotations

import pytest

from quodeq.data.web._response import HttpResponse, check_response_status
from quodeq.data.ports.data_errors import AuthError, NotFoundError, ServerError


class TestCheckResponseStatus:
    def test_auth_error_on_401(self):
        with pytest.raises(AuthError):
            check_response_status(HttpResponse(status=401, data={}))

    def test_auth_error_on_403(self):
        with pytest.raises(AuthError):
            check_response_status(HttpResponse(status=403, data={}))

    def test_not_found_on_404(self):
        with pytest.raises(NotFoundError):
            check_response_status(HttpResponse(status=404, data={}))

    def test_server_error_on_500_includes_status(self):
        """#472 — ServerError message must include the HTTP status code."""
        with pytest.raises(ServerError, match="500"):
            check_response_status(HttpResponse(status=500, data={}))

    def test_server_error_on_503_includes_status(self):
        """#472 — Status code embedded in message for any 5xx."""
        with pytest.raises(ServerError, match="503"):
            check_response_status(HttpResponse(status=503, data={}))

    def test_no_error_on_200(self):
        """2xx responses must not raise."""
        check_response_status(HttpResponse(status=200, data={"ok": True}))
