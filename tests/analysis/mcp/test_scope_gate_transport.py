"""Rule 4 (loopback_transport): transport-encryption findings under a
declared loopback exposure. Split from test_scope_gate.py for the file
size budget; shares the trust models and finding builder with its
test_scope_gate* siblings."""
from __future__ import annotations

from quodeq.analysis.mcp.scope_gate import (
    SCOPE_DOWNGRADE_MARKER,
    apply_scope_gate,
)
from quodeq.context.trust_model import CONSERVATIVE

from ._scope_gate_helpers import LAN, LOCAL, _finding


# --- rule 4: loopback transport -------------------------------------------

def _transport_finding(**kw) -> dict:
    # The boilerplate qwen3.8 stamped on 37 findings of run 5dc4b8b5,
    # verbatim: the exact class this rule exists to cap.
    base = _finding(
        req="S-CON-10",
        w="Cleartext transmission of credentials",
        reason="The application uses Flask without enforcing HTTPS, allowing "
               "sensitive data such as API keys and tokens to be transmitted "
               "in cleartext over the network.",
    )
    base.update(kw)
    return base


def test_transport_req_capped_under_loopback():
    f = _transport_finding()
    assert apply_scope_gate(f, LOCAL) is True
    assert f["severity"] == "minor"
    assert f[SCOPE_DOWNGRADE_MARKER]["rule"] == "loopback_transport"
    assert f[SCOPE_DOWNGRADE_MARKER]["from"] == "major"


def test_transport_req_untouched_under_conservative():
    f = _transport_finding()
    assert apply_scope_gate(f, CONSERVATIVE) is False
    assert f["severity"] == "major"


def test_transport_req_untouched_under_lan():
    # A LAN bind has real on-path observers; only loopback relaxes.
    f = _transport_finding()
    assert apply_scope_gate(f, LAN) is False
    assert f["severity"] == "major"


def test_outbound_transmission_stays_major():
    # Loopback declares who can reach the process, not where it sends data:
    # a credential posted to a third-party endpoint crosses a real wire.
    f = _transport_finding(
        w="API key transmitted in cleartext over HTTP",
        reason="The key is sent in outbound HTTP requests to third-party AI "
               "providers without TLS.",
    )
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "major"


def test_non_transport_prose_under_the_req_is_untouched():
    # Models file non-transport findings under S-CON-10 too; no channel is
    # named, so a loopback declaration has no opinion about them.
    f = _transport_finding(
        w="API key read from environment without protection",
        reason="The provider API key is read from the environment and held "
               "in a plain string for the lifetime of the process.",
    )
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "major"


def test_transport_rule_does_not_gate_other_reqs():
    f = _transport_finding(req="S-CON-9")
    assert apply_scope_gate(f, LOCAL) is False
    assert f["severity"] == "major"
