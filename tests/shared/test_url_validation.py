"""Parity between url_safety_error and validate_url_safe
(shared/url_validation.py): the checker must return exactly the message
the raising twin raises. Covers empty URL, bad scheme, missing host, and
private/loopback addresses (with and without allow_private)."""
from __future__ import annotations

import pytest

from quodeq.shared.url_validation import url_safety_error, validate_url_safe


def test_empty_url():
    with pytest.raises(ValueError) as excinfo:
        validate_url_safe("")
    assert url_safety_error("") == str(excinfo.value)


def test_bad_scheme():
    with pytest.raises(ValueError) as excinfo:
        validate_url_safe("ftp://example.com")
    assert url_safety_error("ftp://example.com") == str(excinfo.value)


def test_missing_host():
    with pytest.raises(ValueError) as excinfo:
        validate_url_safe("http://")
    assert url_safety_error("http://") == str(excinfo.value)


def test_private_address_rejected_by_default():
    with pytest.raises(ValueError) as excinfo:
        validate_url_safe("http://10.0.0.5")
    assert url_safety_error("http://10.0.0.5") == str(excinfo.value)


def test_private_address_allowed_with_allow_private():
    validate_url_safe("http://10.0.0.5", allow_private=True)  # must not raise
    assert url_safety_error("http://10.0.0.5", allow_private=True) is None


def test_loopback_rejected_without_allow_loopback():
    with pytest.raises(ValueError) as excinfo:
        validate_url_safe("http://127.0.0.1")
    assert url_safety_error("http://127.0.0.1") == str(excinfo.value)


def test_loopback_allowed_with_allow_loopback():
    validate_url_safe("http://127.0.0.1", allow_loopback=True)  # must not raise
    assert url_safety_error("http://127.0.0.1", allow_loopback=True) is None


def test_valid_public_url_returns_none():
    validate_url_safe("https://example.com")  # must not raise
    assert url_safety_error("https://example.com") is None
