"""tests/core must not pull framework packages in transitively.

The clean-architecture self-evaluation flagged tests/core files for reaching
httpx (via tests._evidence_helpers -> analysis.mcp.findings_server ->
llm_bridge._embeddings) and pydantic (via data.events). Those chains were cut
by deferring the analysis imports in tests/_evidence_helpers and by moving
the event codec out of the core entities; this test keeps them cut.
"""
from __future__ import annotations

import subprocess
import sys

_PROBE = """
import sys
import tests._evidence_helpers
import quodeq.data.events.reader
import quodeq.data.events.writer
import quodeq.data.actions_log
import quodeq.services.scoring
leaked = [m for m in ("pydantic", "httpx") if m in sys.modules]
assert not leaked, f"framework packages imported transitively: {leaked}"
"""


def test_core_test_helpers_import_no_frameworks():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
