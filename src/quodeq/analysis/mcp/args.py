"""CLI argument parsing for the MCP findings server."""
from __future__ import annotations

import sys

from quodeq.shared.utils import get_findings_file


class ServerArgs:
    """Parsed CLI arguments for the MCP server."""
    findings_file: str = ""
    compiled_dir: str | None = None
    standards_dir: str | None = None
    dimension: str | None = None
    queue_path: str | None = None
    agent_id: str = ""
    work_dir: str | None = None
    cache_root: str | None = None
    model_id: str | None = None
    language: str | None = None

    @property
    def dimensions(self) -> list[str]:
        """Return dimensions as a list (splits comma-separated values)."""
        if not self.dimension:
            return []
        return [d.strip() for d in self.dimension.split(",") if d.strip()]


_FLAG_MAP = {
    "--compiled-dir": "compiled_dir",
    "--standards-dir": "standards_dir",
    "--dimension": "dimension",
    "--queue": "queue_path",
    "--agent-id": "agent_id",
    "--work-dir": "work_dir",
    "--cache-root": "cache_root",
    "--model-id": "model_id",
    "--language": "language",
}

_USAGE = """\
Usage: mcp_findings.py <findings_file> [OPTIONS]

Options:
  --compiled-dir DIR   Directory containing compiled standards
  --standards-dir DIR  Standards root (parent of compiled-dir) used to key
                       the per-file cache -- MUST be config.standards_dir,
                       not compiled-dir, or the params fingerprint looks in
                       the wrong place and silently keys under the
                       default-thresholds key. Falls back to None (no
                       params fingerprint folded into the key) when absent.
  --dimension DIM      Dimension to evaluate
  --queue PATH         Path to the file queue JSON
  --agent-id ID        Agent identifier
  --work-dir DIR       Source repo root for snippet enrichment
  --cache-root DIR     Directory where the per-file cache backend writes entries
                       (typically ~/.quodeq/cache/results/)
  --model-id ID        Model identifier participating in the cache key
  --language LANG      Language identifier participating in the cache key
                       (must match the parent RunConfig.language)
  -h, --help           Show this help message and exit
"""


def parse_args(argv: list[str] | None = None) -> ServerArgs:
    """Parse CLI arguments for the MCP findings server.

    *argv* overrides ``sys.argv[1:]`` when provided, making the parser
    testable without monkeypatching sys.argv.
    """
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

    # Task 3.5: enforce --cache-root and --model-id are present when
    # --dimension is set. Defense-in-depth alongside _build_router's
    # runtime check — fail at parse time, not construction time, so
    # subprocesses spawned without the cache args exit cleanly before
    # doing any work.
    if result.dimension and (not result.cache_root or not result.model_id):
        missing = []
        if not result.cache_root:
            missing.append("--cache-root")
        if not result.model_id:
            missing.append("--model-id")
        sys.stderr.write(
            f"error: {' and '.join(missing)} required when --dimension is "
            "set (needed for synchronous cache writes)\n",
        )
        raise SystemExit(2)

    return result
