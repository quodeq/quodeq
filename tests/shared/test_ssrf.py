"""Tests for shared SSRF protection utility."""
from unittest.mock import patch


from quodeq.shared import ssrf
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


class TestEncodedIPv4Literals:
    """Alternate IPv4 encodings that git/libc resolve into private ranges but
    that ``ipaddress.ip_address`` rejects. They must be canonicalized so SSRF
    via octal/hex/dword/short-form literals is caught (e.g. git clone of
    https://0177.0.0.1/ dials 127.0.0.1)."""

    def test_octal_leading_zero_loopback(self):
        assert is_private_address("0177.0.0.1") is True

    def test_octal_private_10(self):
        assert is_private_address("012.0.0.1") is True

    def test_dword_loopback(self):
        assert is_private_address("2130706433") is True

    def test_hex_loopback(self):
        assert is_private_address("0x7f000001") is True

    def test_hex_dotted_loopback(self):
        assert is_private_address("0x7f.0.0.1") is True

    def test_short_form_loopback(self):
        assert is_private_address("127.1") is True

    def test_public_dotted_literal_still_allowed(self):
        assert is_private_address("8.8.8.8") is False


def test_private_verdict_follows_the_current_dns_answer(monkeypatch):
    """A rebinding host is caught on the lookup that sees the private
    answer: nothing is memoised between calls."""
    answers = iter([[(None, None, None, None, ("140.82.121.3", 0))],
                    [(None, None, None, None, ("127.0.0.1", 0))]])
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", lambda *_a, **_k: next(answers))

    assert ssrf.is_private_address("rebind.example") is False
    assert ssrf.is_private_address("rebind.example") is True


def test_resolve_addresses_returns_literals_and_dns_answers(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda *_a, **_k: [(None, None, None, None, ("140.82.121.3", 0)),
                           (None, None, None, None, ("140.82.121.3", 0)),
                           (None, None, None, None, ("2606:50c0:8000::153", 0, 0, 0))],
    )
    assert ssrf.resolve_addresses("github.com") == ("140.82.121.3", "2606:50c0:8000::153")
    assert ssrf.resolve_addresses("0x7f000001") == ("127.0.0.1",)


def test_resolve_addresses_is_empty_when_dns_fails(monkeypatch):
    def _fail(*_a, **_k):
        raise ssrf.socket.gaierror("no such host")
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _fail)
    assert ssrf.resolve_addresses("nowhere.invalid") == ()
    assert ssrf.is_private_address("nowhere.invalid") is True


def _no_dns(*_args, **_kwargs):
    raise ssrf.socket.gaierror("DNS disabled in this test")


class TestIsLoopbackAddress:
    """is_loopback_address shares resolve_addresses with is_private_address,
    so an encoded loopback literal gets the same verdict from both."""

    # DNS is blocked so the verdict can only come from literal parsing:
    # libc's getaddrinfo happens to accept some encodings, which would hide
    # a weaker literal check.
    def test_hex_loopback_literal(self, monkeypatch):
        monkeypatch.setattr(ssrf.socket, "getaddrinfo", _no_dns)
        assert ssrf.is_loopback_address("0x7f000001") is True

    def test_octal_dword_loopback_literal(self, monkeypatch):
        monkeypatch.setattr(ssrf.socket, "getaddrinfo", _no_dns)
        assert ssrf.is_loopback_address("017700000001") is True

    def test_encoded_private_literal_is_not_loopback(self):
        assert ssrf.is_loopback_address("012.0.0.1") is False

    def test_dns_answer_must_be_all_loopback(self, monkeypatch):
        answers = [(2, 1, 6, "", ("127.0.0.1", 0)), (2, 1, 6, "", ("10.0.0.1", 0))]
        monkeypatch.setattr(ssrf.socket, "getaddrinfo", lambda *_a, **_k: answers)
        assert ssrf.is_loopback_address("mixed.example") is False

    def test_unresolvable_name_is_not_loopback(self, monkeypatch):
        monkeypatch.setattr(ssrf.socket, "getaddrinfo", _no_dns)
        assert ssrf.is_loopback_address("nowhere.example") is False
