"""Static Analysis Manager — manages SA findings as a shrinking work queue.

.. note:: Not yet implemented — tracked in issue SA-INTEGRATION.

   When SA providers are added, this module will be exposed to the LLM
   via an MCP (Model Context Protocol) tool server. The MCP server will
   expose get_findings() and consume_findings() as tools the LLM can call
   during exploration. This keeps the LLM in read-only sandbox mode while
   allowing it to query and consume SA findings through structured tool calls.

Workflow:
    1. SA provider runs before LLM, outputs findings to {dim}_sa.jsonl (archived)
    2. A copy is created as {dim}_sa_pending.jsonl (working queue)
    3. As the LLM explores each file, it calls get_findings(file) via MCP
    4. LLM reconciles SA findings with its own analysis
    5. LLM calls consume_findings(file) to remove processed entries
    6. After free exploration, LLM calls get_remaining() to review unconsumed entries
    7. Pending file shrinks to empty (or near-empty) by end of analysis
"""
from __future__ import annotations

import json
from pathlib import Path


def init_pending(sa_output_path: Path, pending_path: Path) -> None:
    """Copy SA output to a pending work-queue file.

    Args:
        sa_output_path: Path to the original SA output JSONL.
        pending_path: Path to write the pending (working) copy.
    """
    raise NotImplementedError("SA integration not yet available")


def get_findings(pending_path: Path, file_path: str) -> list[dict]:
    """Return SA findings for a specific file from the pending queue.

    Args:
        pending_path: Path to the pending JSONL file.
        file_path: Source file path to filter by.

    Returns:
        List of SA finding dicts for the given file.
    """
    raise NotImplementedError("SA integration not yet available")


def consume_findings(pending_path: Path, file_path: str) -> int:
    """Remove SA findings for a file from the pending queue.

    Args:
        pending_path: Path to the pending JSONL file.
        file_path: Source file path whose findings to remove.

    Returns:
        Number of findings removed.
    """
    raise NotImplementedError("SA integration not yet available")


def get_remaining(pending_path: Path) -> list[dict]:
    """Return all unconsumed SA findings from the pending queue.

    Args:
        pending_path: Path to the pending JSONL file.

    Returns:
        List of all remaining SA finding dicts.
    """
    raise NotImplementedError("SA integration not yet available")
