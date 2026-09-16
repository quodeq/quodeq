"""Python lint gate: the tree must be clean for the ruff rules selected in pyproject.

Same role as tests/tools/test_param_limits.py, but with no grandfathered
baseline: the rule set in [tool.ruff.lint] is narrow on purpose and the
tree is kept at zero. Widen the rule set only with the tree already clean
for the new rule in the same PR.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_PATHS = ["src/quodeq", "tests", "tools"]


def test_ruff_clean():
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format", "concise", *LINT_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        "ruff found violations. Run `uv run ruff check --fix src/quodeq tests tools` "
        "for the autofixable ones and fix the rest by hand:\n"
        + proc.stdout
        + proc.stderr
    )
