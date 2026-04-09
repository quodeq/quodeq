"""Tests for data.web.base_repository — WebRepository base class."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quodeq.data.web.base_repository import WebRepository
from quodeq.data.web._response import HttpResponse
from quodeq.data.ports.data_errors import (
    AuthError,
    InvalidDataError,
    NotFoundError,
    ServerError,
)


def _make_client(status: int, data: object) -> MagicMock:
    client = MagicMock()
    client.get_json.return_value = HttpResponse(status=status, data=data)
    return client


class TestWebRepositoryInit:
    def test_strips_trailing_slash(self):
        repo = WebRepository("https://api.example.com/")
        assert repo._base_url == "https://api.example.com"

    def test_no_trailing_slash(self):
        repo = WebRepository("https://api.example.com")
        assert repo._base_url == "https://api.example.com"

    def test_custom_client(self):
        client = MagicMock()
        repo = WebRepository("https://api.example.com", client=client)
        assert repo._client is client


class TestGetDict:
    def test_successful_dict_response(self):
        client = _make_client(200, {"key": "value"})
        repo = WebRepository("https://api.example.com", client=client)
        result = repo._get_dict("/path")
        assert result == {"key": "value"}
        client.get_json.assert_called_once_with("https://api.example.com/path", {})

    def test_non_dict_response_raises(self):
        client = _make_client(200, ["not", "a", "dict"])
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(InvalidDataError, match="JSON object"):
            repo._get_dict("/path")

    def test_auth_error(self):
        client = _make_client(401, {})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(AuthError):
            repo._get_dict("/path")

    def test_forbidden_error(self):
        client = _make_client(403, {})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(AuthError):
            repo._get_dict("/path")

    def test_not_found_error(self):
        client = _make_client(404, {})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(NotFoundError):
            repo._get_dict("/path")

    def test_server_error(self):
        client = _make_client(500, {})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(ServerError):
            repo._get_dict("/path")


class TestGetList:
    def test_successful_list_response(self):
        client = _make_client(200, {"items": [1, 2, 3]})
        repo = WebRepository("https://api.example.com", client=client)
        result = repo._get_list("/items", "items")
        assert result == [1, 2, 3]

    def test_missing_key_raises(self):
        client = _make_client(200, {"other": "data"})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(InvalidDataError, match="list"):
            repo._get_list("/items", "items")

    def test_non_list_value_raises(self):
        client = _make_client(200, {"items": "not-a-list"})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(InvalidDataError, match="list"):
            repo._get_list("/items", "items")

    def test_empty_list_ok(self):
        client = _make_client(200, {"items": []})
        repo = WebRepository("https://api.example.com", client=client)
        result = repo._get_list("/items", "items")
        assert result == []

    def test_auth_error_propagates(self):
        client = _make_client(401, {})
        repo = WebRepository("https://api.example.com", client=client)
        with pytest.raises(AuthError):
            repo._get_list("/items", "items")
