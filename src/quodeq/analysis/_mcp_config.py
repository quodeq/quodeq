"""MCP configuration file creation for the findings server."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from quodeq.analysis._config import _AgentParams


def _create_mcp_config(
    jsonl_file: Path,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    agent_params: _AgentParams | None = None,
) -> Path:
    """Create a temporary MCP config file pointing to the findings server."""
    ap = agent_params or _AgentParams()
    mcp_script = str(Path(__file__).resolve().parent / "mcp" / "findings_server.py")
    mcp_args = [mcp_script, str(jsonl_file.resolve())]
    if compiled_dir and dimension:
        mcp_args.extend(["--compiled-dir", str(compiled_dir.resolve()), "--dimension", dimension])
    if ap.queue_path:
        mcp_args.extend(["--queue", str(ap.queue_path.resolve())])
    if ap.agent_id:
        mcp_args.extend(["--agent-id", ap.agent_id])
    if ap.work_dir:
        mcp_args.extend(["--work-dir", str(ap.work_dir.resolve())])
    config = {
        "mcpServers": {
            "findings": {
                "command": sys.executable,
                "args": mcp_args,
            }
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="mcp_findings_", delete=False,
    )
    try:
        os.chmod(tmp.name, 0o600)
        json.dump(config, tmp)
    finally:
        tmp.close()
    return Path(tmp.name)
