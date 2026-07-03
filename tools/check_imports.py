#!/usr/bin/env python3
"""Lint script that validates layer import rules for src/quodeq/.

Existing violations are grandfathered via tools/import_baseline.txt so the
gate runs green in CI today while preventing NEW violations. Regenerate the
baseline (only with justification) via:
    python tools/check_imports.py --update-baseline
"""
import re
import sys
from pathlib import Path

LAYER_RULES = {
    "core": {"core"},
    "engine": {"core", "analysis"},
    "data": {"core"},
    "services": {"core", "data"},
    # `update` is a self-contained version-check notifier: it imports nothing
    # from the app (a leaf), and is consumed by api, dashboard, and the CLI.
    # Empty rule + the implicit self/cross-cutting allowances keep it a leaf.
    "update": set(),
    "api": {"core", "services", "update", "assistant"},
    "analysis": {"core", "engine", "data", "services"},
    "dashboard": {"services", "api", "update"},
    "assistant": {"core", "data", "services", "llm_bridge"},
    "terminal": {"core"},
}
CROSS_CUTTING = {"shared", "config"}
IMPORT_RE = re.compile(
    r"^\s*(?:from\s+quodeq\.(\w+)|import\s+quodeq\.(\w+))"
)
SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "quodeq"
BASELINE_PATH = Path(__file__).resolve().parent / "import_baseline.txt"


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
    except (OSError, UnicodeDecodeError) as e:
        print(f"warning: skipping {path}: {e}", file=sys.stderr)
        return violations
    for lineno, line in enumerate(lines, 1):
        m = IMPORT_RE.match(line)
        if not m:
            continue
        target = m.group(1) or m.group(2)
        if target not in allowed:
            violations.append((lineno, target, line.strip()))
    return violations


def collect_violations() -> list[tuple[str, int, str, str]]:
    """Return all (relpath, lineno, target, line) layer-rule violations."""
    all_violations: list[tuple[str, int, str, str]] = []
    for py in sorted(SRC_ROOT.rglob("*.py")):
        layer = source_layer(py)
        if layer is None:
            continue
        for lineno, target, line in check_file(py, layer):
            rel = py.relative_to(SRC_ROOT.parent.parent)
            all_violations.append((rel.as_posix(), lineno, target, line))
    return all_violations


def violation_key(v: tuple[str, int, str, str]) -> str:
    """Identity for a violation, independent of the source line text."""
    filepath, lineno, target, _line = v
    return f"{filepath}:{lineno}:{target}"


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered violation keys (empty if no baseline)."""
    if not path.exists():
        return set()
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write current violations to the baseline file; return the count."""
    keys = sorted(violation_key(v) for v in collect_violations())
    header = (
        "# Grandfathered layer-import violations. Do NOT add entries without\n"
        "# justification -- the goal is to burn this list down, not grow it.\n"
        "# Regenerate intentionally: python tools/check_imports.py --update-baseline\n"
    )
    path.write_text(header + "\n".join(keys) + ("\n" if keys else ""), encoding="utf-8")
    return len(keys)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    unknown = [a for a in args if a != "--update-baseline"]
    if unknown:
        print(f"Unknown argument(s): {' '.join(unknown)}. Usage: check_imports.py [--update-baseline]")
        return 2
    if "--update-baseline" in args:
        n = write_baseline()
        print(f"Wrote {n} violation(s) to {BASELINE_PATH}")
        return 0

    baseline = load_baseline()
    all_violations = collect_violations()
    new = [v for v in all_violations if violation_key(v) not in baseline]
    grandfathered = len(all_violations) - len(new)

    if not new:
        print(f"OK: no new import violations ({grandfathered} grandfathered).")
        return 0
    print(f"Found {len(new)} NEW import violation(s) ({grandfathered} grandfathered):\n")
    for filepath, lineno, target, line in new:
        print(f"  {filepath}:{lineno}  forbidden import of '{target}'")
        print(f"    {line}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
