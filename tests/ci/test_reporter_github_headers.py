"""Every GitHub API call carries the token, the JSON media type and the pinned API version."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.ci.reporter import fetch_pr_changed_lines, post_review


def _capture(body: bytes) -> tuple[list, MagicMock]:
    seen: list = []
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)

    def fake_urlopen(req, timeout):
        seen.append(req)
        return resp

    return seen, fake_urlopen


def test_a_read_sends_auth_accept_and_version_in_order():
    seen, fake = _capture(b"[]")
    with patch("quodeq.ci.reporter.urlopen", side_effect=fake):
        fetch_pr_changed_lines("o", "r", 1, "tok")
    assert seen[0].get_method() == "GET"
    assert seen[0].header_items() == [
        ("Authorization", "Bearer tok"),
        ("Accept", "application/vnd.github+json"),
        ("X-github-api-version", "2022-11-28"),
    ]


def test_a_write_also_declares_its_json_body_before_the_version():
    seen, fake = _capture(b"{}")
    with patch("quodeq.ci.reporter.urlopen", side_effect=fake):
        post_review("o", "r", 1, {"body": "x"}, "tok")
    assert seen[0].get_method() == "POST"
    assert seen[0].data == b'{"body": "x"}'
    assert seen[0].header_items() == [
        ("Authorization", "Bearer tok"),
        ("Accept", "application/vnd.github+json"),
        ("Content-type", "application/json"),
        ("X-github-api-version", "2022-11-28"),
    ]
