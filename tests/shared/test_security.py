"""Tests for the secret-masking helpers in shared/_security.py."""
from __future__ import annotations

from quodeq.shared._security import sanitize_sensitive


def test_masks_equals_form():
    assert "hunter2" not in sanitize_sensitive("password=hunter2")


def test_masks_colon_form():
    assert "abc123" not in sanitize_sensitive("token: abc123")


def test_masks_whitespace_form():
    assert "s3cret" not in sanitize_sensitive("api_key s3cret")


def test_masks_json_shaped_credentials():
    """Regression: the closing quote after the keyword in JSON payloads
    (`"token": "abc"`) used to prevent the pattern from matching."""
    out = sanitize_sensitive('{"token": "abc123", "other": 1}')
    assert "abc123" not in out


def test_masks_json_shaped_api_key():
    out = sanitize_sensitive('{"api_key": "sk-verysecret"}')
    assert "sk-verysecret" not in out


def test_masks_json_single_quoted():
    out = sanitize_sensitive("{'authorization': 'xyz-secret'}")
    assert "xyz-secret" not in out


def test_case_insensitive():
    assert "topsecret" not in sanitize_sensitive("TOKEN=topsecret")


def test_plain_text_untouched():
    text = "no credentials in this line"
    assert sanitize_sensitive(text) == text
