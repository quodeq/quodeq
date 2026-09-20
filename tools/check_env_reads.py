#!/usr/bin/env python3
"""Environment-read ratchet: flag process-environment reads outside the config layer.

Reading `os.environ` deep in the tree makes a unit untestable without
mutating the process and hides a dependency from its callers (flagged by
the self-eval as maintainability `non-injectable-*`, clean-architecture
`env-read-in-inner-layer`, and flexibility). The fix at every site is an
injected `env: Mapping[str, str] | None = None` parameter resolved as
`os.environ if env is None else env` -- never `env or os.environ`, which
turns an injected `{}` back into the process environment (that one is
gated separately by tests/tools/test_no_env_or_fallback.py).

Existing reads are grandfathered in tools/env_reads_baseline.txt so the
gate runs green today while preventing NEW ones. Regenerate the baseline
(only with justification) via:
    python tools/check_env_reads.py --update-baseline

Scans src/**/*.py with `ast` (vendored/generated dirs excluded, see
tools/_ratchet.py:EXCLUDE_DIRS), skipping the config layer that is
allowed to read the environment (ALLOWLIST below). Flagged:
  - any `os.environ` / `os.getenv` attribute on the `os` module, however
    it is used: `.get`, subscript, `.copy()`, `in os.environ`, or passed
    along as an argument (an alias from `import os as _os` counts)
  - a bare `environ` / `getenv` loaded after `from os import environ`
    (an `as` alias counts)
Comments and strings are invisible to `ast`, so they are never flagged.

Entries are line-keyed (relpath:lineno), so an unrelated line-count change
above a grandfathered read shifts its entry. Prefer hand-editing the
baseline over blind --update-baseline regeneration, which can silently
absorb a genuinely new read introduced in the same change. One line is one
entry even when it reads the environment twice.

Known limitations, documented rather than closed (none happens by
accident): a module that both does `from os import environ` and binds a
local named `environ` has that local's loads flagged too (the finder
resolves by spelling, not by scope); and a name bound to `os.environ`
first (`e = os.environ`) is keyed at the binding line only. `os.environb`,
`os.getenvb`, `os.putenv`, and `os.unsetenv` are not flagged (nothing in
src uses them).
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import _ratchet

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
BASELINE_PATH = Path(__file__).resolve().parent / "env_reads_baseline.txt"

# Paths (relative to the repo root) that own environment access. An entry
# ending in "/" is a directory prefix, one ending in ".py" is an exact
# file, and anything else is a file-name prefix within its own directory
# (so `src/quodeq/shared/env` covers env.py, env_paths.py, env_resolve.py and
# every future sibling, but not `src/quodeq/shared/frozen.py`).
ALLOWLIST = (
    "src/quodeq/shared/env",
    "src/quodeq/shared/_env",
    "src/quodeq/config/",
    "src/quodeq/_cli_env.py",
)

_ENV_NAMES = frozenset({"environ", "getenv"})


@dataclass(frozen=True, slots=True)
class Hit:
    """One environment read: where it is, and the source line that does it."""

    path: Path
    line: int
    key: str
    source: str


def _matches(rel: str, entry: str) -> bool:
    if entry.endswith("/"):
        return rel.startswith(entry)
    if entry.endswith(".py"):
        return rel == entry
    return rel.startswith(entry) and "/" not in rel[len(entry):]


def is_allowed(rel: str) -> bool:
    """True if *rel* (a repo-relative posix path) is in the config layer."""
    return any(_matches(rel, entry) for entry in ALLOWLIST)


def _os_module_names(tree: ast.Module) -> set[str]:
    """Names bound to the `os` module by `import os` / `import os as X`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            if alias.asname is not None:
                if alias.name == "os":
                    names.add(alias.asname)
            elif alias.name == "os" or alias.name.startswith("os."):
                names.add("os")
    return names


def _bare_env_names(tree: ast.Module) -> set[str]:
    """Names bound by `from os import environ` / `getenv` (aliases included)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "os" or node.level:
            continue
        names |= {
            alias.asname or alias.name
            for alias in node.names
            if alias.name in _ENV_NAMES
        }
    return names


def env_read_lines(tree: ast.Module) -> list[int]:
    """Return the sorted line numbers on which *tree* reads the environment."""
    os_names = _os_module_names(tree)
    bare_names = _bare_env_names(tree)
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (node.attr in _ENV_NAMES
                    and isinstance(node.value, ast.Name)
                    and node.value.id in os_names):
                lines.add(node.lineno)
        elif (isinstance(node, ast.Name)
                and node.id in bare_names
                and isinstance(node.ctx, ast.Load)):
            lines.add(node.lineno)
    return sorted(lines)


def scan_tree(root: Path) -> list[Hit]:
    """Return every environment read under *root* (a `src` directory)."""
    hits: list[Hit] = []
    for py in _ratchet.iter_python_files(root):
        rel = py.relative_to(root.parent).as_posix()
        if is_allowed(rel):
            continue
        text = _ratchet.read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        source = text.splitlines()
        for line in env_read_lines(tree):
            text_at = source[line - 1].strip() if line <= len(source) else ""
            hits.append(Hit(path=py, line=line, key=f"{rel}:{line}", source=text_at))
    return hits


def _scan() -> list[Hit]:
    """Return all environment reads in src/, sorted by key."""
    return sorted(scan_tree(SRC_ROOT), key=violation_key)


def violation_key(hit: Hit) -> str:
    """Identity for a read: relpath:lineno."""
    return hit.key


def describe(hit: Hit) -> str:
    """One-line report of a read, with the offending source line."""
    return f"{hit.key}: {hit.source}"


def collect_violations() -> list[str]:
    """Return baseline keys for all current environment reads."""
    return sorted({violation_key(hit) for hit in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered read keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write current environment reads to the baseline file; return the count."""
    header = (
        "# Grandfathered process-environment reads (os.environ / os.getenv\n"
        "# outside the config layer). Do NOT add entries without\n"
        "# justification -- the goal is to burn this list to zero, not grow it.\n"
        "# The fix is an injected `env: Mapping[str, str] | None = None`\n"
        "# parameter resolved as `os.environ if env is None else env`.\n"
        "# Regenerate intentionally: python tools/check_env_reads.py --update-baseline\n"
        "# Entries are line-keyed (relpath:lineno), so an unrelated line-count\n"
        "# change above a grandfathered read shifts its entry. Prefer hand-editing\n"
        "# the baseline over blind --update-baseline regeneration, which can\n"
        "# silently absorb a genuinely new read introduced in the same change.\n"
    )
    return _ratchet.write_baseline(path, header, collect_violations())


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_env_reads.py [--update-baseline]`."""
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_env_reads.py",
        noun="environment-read",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=describe,
    ))


if __name__ == "__main__":
    sys.exit(main())
