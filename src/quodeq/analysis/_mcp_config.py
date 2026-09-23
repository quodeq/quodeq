"""MCP configuration file creation for the findings server."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from quodeq.analysis._config import AgentParams
from quodeq.analysis.cache.local import default_cache_root as _default_cache_root
from quodeq.shared.mcp import codex_mcp_override

_SERVER_NAME = "findings"
_SERVER_MODULE = ["-m", "quodeq.analysis.mcp.findings_server"]


def _findings_server_args(
    compiled_dir: Path | None, dimension: str | None, ap: AgentParams,
) -> list[str]:
    """Build the findings-server flags shared by the config file and the
    Codex ``-c`` override, so the two spawn paths never drift."""
    args: list[str] = []
    if compiled_dir and dimension:
        args.extend(["--compiled-dir", str(compiled_dir.resolve()), "--dimension", dimension])
    if ap.standards_dir:
        args.extend(["--standards-dir", str(ap.standards_dir.resolve())])
    if ap.queue_path:
        args.extend(["--queue", str(ap.queue_path.resolve())])
    if ap.agent_id:
        args.extend(["--agent-id", ap.agent_id])
    if ap.work_dir:
        args.extend(["--work-dir", str(ap.work_dir.resolve())])
    # Cache fingerprint inputs (cache_root + model_id +
    # language) MUST be emitted on every spawn so the subprocess writes cache
    # entries with the same keys as classify_files_via_cache. Defaults match
    # cache.dimension_helpers._model_id_from ('unknown') and the
    # language-unset contract ('').
    args.extend([
        "--cache-root", str(_default_cache_root()),
        "--model-id", ap.model_id or "unknown",
        "--language", ap.language or "",
    ])
    return args


def create_mcp_config(
    jsonl_file: Path,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    agent_params: AgentParams | None = None,
    *,
    tools: list[str] | None = None,
) -> Path:
    """Create a temporary MCP config file pointing to the findings server."""
    ap = agent_params or AgentParams()
    mcp_script = str(Path(__file__).resolve().parent / "mcp" / "findings_server.py")
    mcp_args = [
        mcp_script, str(jsonl_file.resolve()),
        *_findings_server_args(compiled_dir, dimension, ap),
    ]
    config = {
        "mcpServers": {
            _SERVER_NAME: {
                "command": sys.executable,
                "args": mcp_args,
            }
        }
    }
    if tools is not None:
        config["mcpServers"][_SERVER_NAME]["tools"] = tools
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="mcp_findings_", delete=False,
    )
    try:
        os.chmod(tmp.name, 0o600)
        json.dump(config, tmp)
    finally:
        tmp.close()
    return Path(tmp.name)


def codex_mcp_config_arg(
    jsonl_file: Path,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    agent_params: AgentParams | None = None,
) -> str:
    """Return a Codex ``-c`` TOML override for the findings MCP server."""
    ap = agent_params or AgentParams()
    args = [
        *_SERVER_MODULE, str(jsonl_file.resolve()),
        *_findings_server_args(compiled_dir, dimension, ap),
    ]
    return codex_mcp_override(_SERVER_NAME, args)
