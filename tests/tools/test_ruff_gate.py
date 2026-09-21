"""Python lint gate: the tree must be clean for the ruff rules selected in pyproject.

Same role as tests/tools/test_param_limits.py, but with no grandfathered
baseline: the rule set in [tool.ruff.lint] is narrow on purpose and the
tree is kept at zero. Widen the rule set only with the tree already clean
for the new rule in the same PR.
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_PATHS = ["src/quodeq", "tests", "tools"]
MAX_COMPLEXITY = 15
DOCSTRING_CODES = ["D100", "D101", "D102", "D103", "D104"]


def test_complexity_gate_selected():
    """C901 is part of the selected rule set at the standard's ceiling, so
    test_ruff_clean below also proves no function exceeds it."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        lint = tomllib.load(fh)["tool"]["ruff"]["lint"]
    assert "C901" in lint["select"]
    assert lint["mccabe"]["max-complexity"] == MAX_COMPLEXITY
    ignored = [rules for rules in lint.get("per-file-ignores", {}).values() if "C901" in rules]
    assert not ignored, "C901 must not be ignored per file"


def test_docstring_gate_selected():
    """D100-D104 are selected and ignored only for tests/ and tools/, so
    test_ruff_clean below also proves every public module, package, class,
    method and function under src/quodeq is documented (M-ANA-5)."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        lint = tomllib.load(fh)["tool"]["ruff"]["lint"]
    missing = [code for code in DOCSTRING_CODES if code not in lint["select"]]
    assert not missing, f"docstring codes dropped from the gate: {missing}"
    assert lint["pydocstyle"]["convention"] == "pep257"
    ignoring = {
        pattern for pattern, rules in lint.get("per-file-ignores", {}).items()
        if any(code in rules for code in DOCSTRING_CODES)
    }
    assert ignoring == {"tests/**", "tools/**"}, (
        "D1xx may only be ignored for tests/ and tools/; src/quodeq is the "
        f"documented surface. Got: {sorted(ignoring)}"
    )


def test_unused_argument_gate_selected():
    """ARG is selected and ignored only for tests/, so test_ruff_clean below
    also proves src/quodeq and tools/ carry no unused argument (M-ANA-10)."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        lint = tomllib.load(fh)["tool"]["ruff"]["lint"]
    assert "ARG" in lint["select"]
    ignoring = {
        pattern for pattern, rules in lint.get("per-file-ignores", {}).items()
        if "ARG" in rules
    }
    assert ignoring == {"tests/**"}, (
        "ARG may only be ignored for tests/, where fakes must match the "
        f"signature they stand in for. Got: {sorted(ignoring)}"
    )


def test_undefined_name_gate_selected():
    """F821 is selected everywhere, so test_ruff_clean below also proves no
    module references a name it never defines or imports.

    Pinned because the whole tree, tests included, is the surface: a name that
    only appears on an error branch (a logger in an except handler, say) would
    otherwise reach production as a NameError.
    """
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        lint = tomllib.load(fh)["tool"]["ruff"]["lint"]
    assert "F821" in lint["select"]
    ignoring = [
        pattern for pattern, rules in lint.get("per-file-ignores", {}).items()
        if "F821" in rules
    ]
    assert not ignoring, f"F821 must not be ignored per file. Got: {ignoring}"


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
