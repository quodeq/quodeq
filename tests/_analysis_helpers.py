"""Shared analysis-layer test helpers (split out of tests/_evidence_helpers.py).

These helpers pull in the analysis layer (and its transitive framework
dependencies) so they're kept separate from tests/_evidence_helpers.py, which
stays a pure module usable from tests/core.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import patch

from quodeq.analysis.mcp import findings_server as mcp_findings
from quodeq.analysis.subagents.file_queue import FileQueue

from tests._evidence_helpers import _make_request  # noqa: F401 — re-export


def _fake_run_analysis(work_dir, prompt, stream_file, config):
    """Mock run_analysis that writes some findings and drains the queue."""
    stream_file.parent.mkdir(parents=True, exist_ok=True)
    stream_file.write_text("")
    if config.queue_path:
        queue = FileQueue(config.queue_path)
        queue.take(queue.remaining(), agent_id=config.agent_id)
    if config.jsonl_file:
        agent_id = config.agent_id or "unknown"
        with open(config.jsonl_file, "a") as f:
            f.write(json.dumps({
                "schema_version": 1,
                "p": "Modularity", "t": "violation", "d": "maintainability",
                "w": f"Found by {agent_id}", "file": f"{agent_id}.py", "line": 1,
            }) + "\n")


def _run_server(input_lines: list[str], findings_file: str) -> list[dict]:
    """Feed *input_lines* to the MCP server and return parsed response dicts."""
    stdin_text = "\n".join(input_lines) + "\n"
    stdout_buf = StringIO()
    with patch.object(sys, "stdin", StringIO(stdin_text)), \
         patch.object(sys, "stdout", stdout_buf), \
         patch.object(sys, "argv", ["mcp_findings.py", findings_file]):
        mcp_findings.main()
    output = stdout_buf.getvalue().strip()
    return [json.loads(line) for line in output.splitlines() if line.strip()]
