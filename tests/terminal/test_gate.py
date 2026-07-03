from quodeq.terminal.gate import terminal_gate_reason

OK = dict(host="127.0.0.1", api_key=None, origin="http://localhost:7863", request_host="localhost:7863")


def test_allows_loopback_local_matching_origin():
    assert terminal_gate_reason(**OK) is None
    assert terminal_gate_reason(**{**OK, "host": "::1"}) is None


def test_refuses_non_loopback_bind():
    assert terminal_gate_reason(**{**OK, "host": "0.0.0.0"}) is not None
    assert terminal_gate_reason(**{**OK, "host": "192.168.1.5"}) is not None


def test_refuses_when_api_key_remote_mode():
    assert terminal_gate_reason(**{**OK, "api_key": "secret"}) is not None


def test_refuses_missing_or_mismatched_origin():
    assert terminal_gate_reason(**{**OK, "origin": None}) is not None
    assert terminal_gate_reason(**{**OK, "origin": "http://evil.example"}) is not None


def test_refuses_dns_rebinding_origin_equals_host_but_host_not_loopback():
    # Origin == Host passes the origin check, but the Host is not a loopback
    # name -> DNS-rebinding attempt must still be refused.
    assert terminal_gate_reason(
        host="127.0.0.1", api_key=None,
        origin="http://evil.com:7863", request_host="evil.com:7863",
    ) is not None
    assert terminal_gate_reason(
        host="127.0.0.1", api_key=None,
        origin="http://evil.com", request_host="evil.com",
    ) is not None


def test_allows_port_suffixed_loopback_host():
    assert terminal_gate_reason(
        host="127.0.0.1", api_key=None,
        origin="http://localhost:7863", request_host="localhost:7863",
    ) is None


def test_allows_bracketed_ipv6_loopback_host():
    assert terminal_gate_reason(
        host="::1", api_key=None,
        origin="http://[::1]:7863", request_host="[::1]:7863",
    ) is None
