#!/usr/bin/env python3
"""Lint script that validates layer import rules for src/quodeq/."""
import re
import sys
from pathlib import Path

LAYER_RULES = {
    "core": {"core"},
    "engine": {"core"},
    "data": {"core"},
    "services": {"core", "data"},
    "api": {"core", "services"},
    "analysis": {"core", "engine", "data", "services"},
    "dashboard": {"services", "api"},
}
CROSS_CUTTING = {"shared", "config"}
IMPORT_RE = re.compile(
    r"^\s*(?:from\s+quodeq\.(\w+)|import\s+quodeq\.(\w+))"
)
SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "quodeq"


def source_layer(path: Path) -> str | None:
    """Return the layer name for a file, or None if not in a known layer."""
    rel = path.relative_to(SRC_ROOT)
    top = rel.parts[0] if rel.parts else None
    return top if top in LAYER_RULES else None


def check_file(path: Path, layer: str) -> list[tuple[int, str, str]]:
    """Return list of (lineno, target_layer, line) violations."""
    violations = []
    allowed = LAYER_RULES[layer] | CROSS_CUTTING | {layer}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return violations
    for lineno, line in enumerate(lines, 1):
        m = IMPORT_RE.match(line)
        if not m:
            continue
        target = m.group(1) or m.group(2)
        if target not in allowed:
            violations.append((lineno, target, line.strip()))
    return violations


def main() -> int:
    all_violations: list[tuple[str, int, str, str]] = []
    for py in sorted(SRC_ROOT.rglob("*.py")):
        layer = source_layer(py)
        if layer is None:
            continue
        for lineno, target, line in check_file(py, layer):
            rel = py.relative_to(SRC_ROOT.parent.parent)
            all_violations.append((str(rel), lineno, target, line))
    if not all_violations:
        print("OK: no violations")
        return 0
    print(f"Found {len(all_violations)} import violation(s):\n")
    for filepath, lineno, target, line in all_violations:
        print(f"  {filepath}:{lineno}  forbidden import of '{target}'")
        print(f"    {line}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
