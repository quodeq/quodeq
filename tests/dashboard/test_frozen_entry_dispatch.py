"""The desktop bundle's entry script starts the MCP servers on their private flags.

Agent CLIs launch ``Quodeq --_mcp_findings ...`` and ``Quodeq --_mcp_assistant
...`` and speak JSON-RPC over stdio. Falling through to the dashboard CLI
there prints a usage error and the scan records no findings.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from quodeq.shared import frozen

_ENTRY = Path(__file__).resolve().parents[2] / "packaging" / "macos" / "dashboard_entry.py"
_SERVER_MAINS = {
    frozen.MCP_FINDINGS: "quodeq.analysis.mcp.findings_server.main",
    frozen.MCP_ASSISTANT: "quodeq.assistant.mcp.server.main",
}


@pytest.fixture
def entry():
    spec = importlib.util.spec_from_file_location("quodeq_dashboard_entry", _ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seen(monkeypatch):
    """Replace both servers and the dashboard CLI, recording what ran and with which argv."""
    ran: list[tuple[str, list[str]]] = []
    for server, target in _SERVER_MAINS.items():
        monkeypatch.setattr(target, lambda *_a, server=server: ran.append((server, list(sys.argv))))
    monkeypatch.setattr("quodeq.dashboard.cli.main", lambda *_a: ran.append(("dashboard", [])) or 2)
    return ran


@pytest.mark.parametrize("server", sorted(_SERVER_MAINS))
def test_private_flag_runs_the_server_with_the_flag_stripped(entry, seen, monkeypatch, server):
    with monkeypatch.context() as patched:
        patched.setattr(sys, "frozen", True, raising=False)
        argv = frozen.mcp_server_cmd(server, ["unused"], ["/run/f.jsonl", "--language", ""])
    monkeypatch.setattr(sys, "argv", ["Quodeq", *argv[1:]])
    assert entry.main() == 0
    assert seen == [(server, ["Quodeq", "/run/f.jsonl", "--language", ""])]


@pytest.mark.parametrize("server", sorted(_SERVER_MAINS))
def test_frozen_server_skips_the_login_shell(entry, seen, monkeypatch, server):
    """The login shell that discovers PATH would share the JSON-RPC stdin."""
    shells: list[str] = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
    monkeypatch.setenv("QUODEQ_STATIC_DIST", "/bundle/quodeq/static")
    monkeypatch.setattr("quodeq.dashboard._frozen.source_user_path", lambda: shells.append("ran"))
    monkeypatch.setattr(sys, "argv", ["Quodeq", f"--_{server}", "/run/f.jsonl"])
    assert entry.main() == 0
    assert shells == []
    assert [name for name, _ in seen] == [server]


def test_other_arguments_still_reach_the_dashboard_cli(entry, seen, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "argv", ["Quodeq", "--no-open"])
    assert entry.main() == 2
    assert seen == [("dashboard", [])]
