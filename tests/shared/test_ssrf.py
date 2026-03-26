"""Tests for shared SSRF protection utility."""
from unittest.mock import patch

import pytest

from quodeq.shared.ssrf import is_private_address


class TestIsPrivateAddress:
    def test_localhost(self):
        assert is_private_address("localhost") is True

    def test_localhost_localdomain(self):
        assert is_private_address("localhost.localdomain") is True

    def test_ipv4_loopback(self):
        assert is_private_address("127.0.0.1") is True

    def test_ipv4_private_10(self):
        assert is_private_address("10.0.0.1") is True

    def test_ipv4_private_192(self):
        assert is_private_address("192.168.1.1") is True

    def test_ipv4_private_172(self):
        assert is_private_address("172.16.0.1") is True

    def test_ipv6_loopback(self):
        assert is_private_address("::1") is True

    def test_public_ip(self):
        assert is_private_address("8.8.8.8") is False

    @patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('140.82.121.3', 0))])
    def test_public_hostname(self, _mock_dns):
        assert is_private_address("github.com") is False

    def test_link_local(self):
        assert is_private_address("169.254.1.1") is True
