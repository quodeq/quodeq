"""CLI argument parsing for the MCP findings server."""
from __future__ import annotations

import sys


class ServerArgs:
    """Parsed CLI arguments for the MCP server."""
    findings_file: str = ""
    compiled_dir: str | None = None
    dimension: str | None = None
    queue_path: str | None = None
    agent_id: str = ""


_FLAG_MAP = {
    "--compiled-dir": "compiled_dir",
    "--dimension": "dimension",
    "--queue": "queue_path",
    "--agent-id": "agent_id",
}

_USAGE = """\
Usage: mcp_findings.py <findings_file> [OPTIONS]

Options:
  --compiled-dir DIR   Directory containing compiled standards
  --dimension DIM      Dimension to evaluate
  --queue PATH         Path to the file queue JSON
  --agent-id ID        Agent identifier
  -h, --help           Show this help message and exit
"""


def parse_args(argv: list[str] | None = None) -> ServerArgs:
    """Parse CLI arguments for the MCP findings server.

    *argv* overrides ``sys.argv[1:]`` when provided, making the parser
    testable without monkeypatching sys.argv.
    """
    from quodeq.shared.utils import get_findings_file

    result = ServerArgs()
    args = argv if argv is not None else sys.argv[1:]

    if "--help" in args or "-h" in args:
        sys.stdout.write(_USAGE)
        raise SystemExit(0)

    i = 0
    while i < len(args):
        if args[i] in _FLAG_MAP and i + 1 < len(args):
            setattr(result, _FLAG_MAP[args[i]], args[i + 1])
            i += 2
        elif not args[i].startswith("--"):
            result.findings_file = args[i]
            i += 1
        else:
            sys.stderr.write(f"Warning: unrecognised argument '{args[i]}'\n")
            i += 1

    if not result.findings_file:
        result.findings_file = get_findings_file() or ""
    return result
