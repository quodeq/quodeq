"""Release everything one CLI turn acquired: process, timer, scratch cwd, MCP config."""
from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quodeq.assistant.adapters._cli_command import McpConfigRef
from quodeq.assistant.mcp import _config as mcp_config
from quodeq.core.constants import MCP_STYLE_CLI_REGISTER
from quodeq.shared.process_kill import kill_proc_tree as _kill_proc_tree


@dataclass
class TurnResources:
    """What a turn has acquired so far; every field stays None until it exists."""

    proc: Any = None
    timer: threading.Timer | None = None
    cwd: str | None = None
    sandbox_cleanup: Callable[[], None] | None = None


def release_turn_resources(
    resources: TurnResources, *, mcp_config_ref: McpConfigRef, cli_cfg: Any,
) -> None:
    """Tear down *resources* in dependency order, tolerating fields never acquired."""
    if resources.timer is not None:
        resources.timer.cancel()
    if resources.proc is not None and resources.proc.poll() is None:
        _kill_proc_tree(resources.proc)
    if mcp_config_ref.path:
        Path(mcp_config_ref.path).unlink(missing_ok=True)
    if resources.sandbox_cleanup is not None:
        resources.sandbox_cleanup()
    if cli_cfg.mcp_style == MCP_STYLE_CLI_REGISTER:
        mcp_config.unregister_cli_mcp(cli_cfg.cmd)
    if resources.cwd is not None:
        shutil.rmtree(resources.cwd, ignore_errors=True)
