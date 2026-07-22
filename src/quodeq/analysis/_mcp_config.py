"""MCP configuration file creation for the findings server."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from quodeq.analysis._config import _AgentParams
from quodeq.shared._mcp import codex_mcp_override

_SERVER_NAME = "findings"
_SERVER_MODULE = ["-m", "quodeq.analysis.mcp.findings_server"]


def _default_cache_root():
    """Return the result cache root, honouring QUODEQ_CACHE_ROOT.

    Deferred import breaks the circular dependency:
    _mcp_config -> cache/__init__ -> dimension_helpers -> _types -> subprocess -> _command -> _mcp_config.
    """
    from quodeq.analysis.cache.local import default_cache_root  # noqa: PLC0415
    return default_cache_root()


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
    if ap.standards_dir:
        mcp_args.extend(["--standards-dir", str(ap.standards_dir.resolve())])
    if ap.queue_path:
        mcp_args.extend(["--queue", str(ap.queue_path.resolve())])
    if ap.agent_id:
        mcp_args.extend(["--agent-id", ap.agent_id])
    if ap.work_dir:
        mcp_args.extend(["--work-dir", str(ap.work_dir.resolve())])
    # Phase 1.5 (Task 3.5): cache fingerprint inputs (cache_root + model_id +
    # language) MUST be emitted on every spawn so the subprocess writes cache
    # entries with the same keys as classify_files_via_cache. Defaults match
    # cache.dimension_helpers._model_id_from ('unknown') and Task 5's
    # language-unset contract ('').
    mcp_args.extend([
        "--cache-root", str(_default_cache_root()),
        "--model-id", ap.model_id or "unknown",
        "--language", ap.language or "",
    ])
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


def _codex_mcp_config_arg(
    jsonl_file: Path,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    agent_params: _AgentParams | None = None,
) -> str:
    """Return a Codex ``-c`` TOML override for the findings MCP server."""
    ap = agent_params or _AgentParams()
    args = [*_SERVER_MODULE, str(jsonl_file.resolve())]
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
    args.extend([
        "--cache-root", str(_default_cache_root()),
        "--model-id", ap.model_id or "unknown",
        "--language", ap.language or "",
    ])
    return codex_mcp_override(_SERVER_NAME, args)
