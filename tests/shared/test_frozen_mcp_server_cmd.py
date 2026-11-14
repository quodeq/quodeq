"""The argv an agent CLI runs to start a Quodeq MCP server.

From source the interpreter runs a script or a module. The desktop bundle's
``sys.executable`` is the Quodeq binary, which only understands the private
``--_<server>`` flags its entry script dispatches on.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from quodeq.shared import frozen

_SERVERS = [frozen.MCP_FINDINGS, frozen.MCP_ASSISTANT]


def _frozen(value: bool):
    return patch.object(sys, "frozen", value, create=True)


def test_unfrozen_runs_a_module_through_the_interpreter():
    with _frozen(False):
        cmd = frozen.mcp_server_cmd(frozen.MCP_ASSISTANT, ["-m", "pkg.server"], ["--db-path", "/x"])
    assert cmd == [sys.executable, "-m", "pkg.server", "--db-path", "/x"]


def test_unfrozen_runs_a_script_through_the_interpreter():
    with _frozen(False):
        cmd = frozen.mcp_server_cmd(frozen.MCP_FINDINGS, ["/src/findings_server.py"], ["/run/f.jsonl"])
    assert cmd == [sys.executable, "/src/findings_server.py", "/run/f.jsonl"]


@pytest.mark.parametrize("server", _SERVERS)
def test_frozen_uses_the_private_flag_and_drops_the_launcher(server):
    with _frozen(True):
        cmd = frozen.mcp_server_cmd(server, ["-m", "pkg.server"], ["--flag", "v"])
    assert cmd == [sys.executable, f"--_{server}", "--flag", "v"]


@pytest.mark.parametrize("is_frozen", [True, False])
def test_args_are_optional(is_frozen):
    with _frozen(is_frozen):
        cmd = frozen.mcp_server_cmd(frozen.MCP_FINDINGS, ["script.py"])
    assert cmd == [sys.executable, "--_mcp_findings" if is_frozen else "script.py"]
