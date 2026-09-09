"""Tests for the shared dashboard alt-port constants (security.py's
_ALT_PORT_ORIGINS and useServerHealth.js's altPortCandidates() both derive
from this module).
"""
from __future__ import annotations

import json
from pathlib import Path

import quodeq.shared as shared_pkg
from quodeq.shared.dashboard_ports import DASHBOARD_BASE_PORT, alt_port_origins, alt_ports


def test_dashboard_base_port_matches_defaults_json():
    """DASHBOARD_BASE_PORT is a literal so it must be kept in sync by hand
    with shared/defaults.json's dashboard_port (which get_dashboard_port()
    reads, env-overridable) -- this pins that the two never drift apart."""
    defaults_path = Path(shared_pkg.__file__).resolve().parent / "defaults.json"
    with open(defaults_path) as f:
        defaults = json.load(f)
    assert DASHBOARD_BASE_PORT == defaults["dashboard_port"]


def test_alt_port_origins_covers_every_port_both_hosts_both_schemes():
    tokens = alt_port_origins().split()
    ports = alt_ports()
    assert len(ports) > 0
    for port in ports:
        for host in ("127.0.0.1", "localhost"):
            for scheme in ("http", "ws"):
                assert f"{scheme}://{host}:{port}" in tokens
