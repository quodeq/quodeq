"""tests/core must not pull framework packages in transitively.

The clean-architecture self-evaluation flagged tests/core files for reaching
httpx (via tests._evidence_helpers -> analysis.mcp.findings_server ->
llm_bridge._embeddings) and pydantic (via analysis.mcp.handlers -> quodeq ->
quodeq.cli). Those chains were cut by splitting the analysis-layer helpers
out of tests/_evidence_helpers into tests/_analysis_helpers; this test keeps
them cut, using both a runtime import probe and a static checker-based guard.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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


def test_tests_core_has_no_transitive_framework_dependency():
    from quodeq.core.checks.framework_deps import check_framework_dependencies
    from quodeq.core.checks.frameworks import FRAMEWORK_PACKAGES
    from quodeq.data.fs.import_graph import build_import_graph

    root = Path(__file__).resolve().parents[2]
    files = [*(root / "src").rglob("*.py"), *(root / "tests").rglob("*.py")]
    graph = build_import_graph(root, files)
    judgments = check_framework_dependencies(graph, framework_packages=FRAMEWORK_PACKAGES, dimension="architecture")
    offenders = [j for j in judgments if j.practice_id == "CLEA-DEP-06" and j.file.startswith("tests/core/")]
    assert not offenders, [(j.file, j.reason) for j in offenders]
