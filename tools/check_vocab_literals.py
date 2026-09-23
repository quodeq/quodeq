#!/usr/bin/env python3
"""Vocabulary-literal ratchet: flag bare state/severity/grade strings in comparisons.

Closed vocabularies (run state, job status, exit reason, severity, grade,
file-done status, dimension state, provider) are StrEnums in one home module
each (HOME_MODULES). Writing one of their values as a bare string where the
code branches on it -- `s == "running"`, `s in {"done", "failed"}`,
`case "cancelled":`, `status="done"`, `{"status": "done"}` -- is what this
gate flags (maintainability M-MDF-1, and the typo class nothing else catches).
The fix is the enum member: `s == RunState.RUNNING`.

Not flagged: dict keys, f-strings, docstrings, log/message arguments, and
any string that is not in VOCAB_WORDS. Home modules are exempt.

Entries are line-keyed (relpath:lineno:literal). Regenerate intentionally:
    python tools/check_vocab_literals.py --update-baseline
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ratchet  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
BASELINE_PATH = REPO_ROOT / "tools" / "vocab_literals_baseline.txt"

HOME_MODULES = frozenset({
    "quodeq/core/run/state.py",
    "quodeq/core/run/job_status.py",
    "quodeq/core/run/exit_reason.py",
    "quodeq/core/run/dimensions.py",
    "quodeq/core/types/severity.py",
    "quodeq/core/scoring/constants.py",
    "quodeq/analysis/mcp/schemas.py",
    "quodeq/config/provider.py",
})

VOCAB_WORDS = frozenset({
    # RunState + legacy spellings
    "pending", "running", "finalizing", "done", "failed", "cancelled",
    "complete", "completed", "finished", "in_progress", "canceled", "lost",
    # ExitReason
    "time_limit", "deadline", "failure_streak", "error",
    "stale_detected", "stale_legacy_pid_dead", "stale_legacy_no_pid",
    # Severity
    "critical", "major", "minor",
    # Grade
    "Exemplary", "Good", "Adequate", "Poor", "Insufficient",
    # FileDoneStatus
    "ok", "skipped",
    # DimState
    "incomplete",
    # Provider
    "claude", "codex", "gemini", "copilot", "ollama", "llamacpp", "openrouter", "custom",
})

VOCAB_KEYWORDS = frozenset({"status", "state", "severity", "grade", "run_state", "exit_reason", "provider"})


@dataclass(frozen=True, slots=True)
class Hit:
    path: Path
    line: int
    literal: str
    key: str
    source: str


def _vocab_constants(node: ast.AST) -> list[ast.Constant]:
    """The vocabulary string constants directly inside a comparator node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in VOCAB_WORDS:
        return [node]
    if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        return [c for elt in node.elts for c in _vocab_constants(elt)]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"} and node.args:
        return _vocab_constants(node.args[0])
    return []


def _match_constants(pattern: ast.AST) -> list[ast.Constant]:
    """The vocabulary string constants a `case` pattern matches against."""
    out: list[ast.Constant] = []
    for sub in ast.walk(pattern):
        if isinstance(sub, ast.MatchValue):
            out.extend(_vocab_constants(sub.value))
    return out


class _Finder(ast.NodeVisitor):
    """Collects every vocabulary constant sitting in a branching position."""

    def __init__(self) -> None:
        self.found: list[ast.Constant] = []

    def visit_Compare(self, node: ast.Compare) -> None:
        for operand in [node.left, *node.comparators]:
            self.found.extend(_vocab_constants(operand))
        self.generic_visit(node)

    def visit_match_case(self, node: ast.match_case) -> None:
        self.found.extend(_match_constants(node.pattern))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg in VOCAB_KEYWORDS:
                self.found.extend(_vocab_constants(kw.value))
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value in VOCAB_KEYWORDS:
                self.found.extend(_vocab_constants(value))
        self.generic_visit(node)


def scan_tree(src_root: Path) -> list[Hit]:
    """Every bare vocabulary literal in a branching position under src_root."""
    hits: list[Hit] = []
    for py in _ratchet.iter_python_files(src_root):
        rel = py.relative_to(src_root).as_posix()
        if rel in HOME_MODULES:
            continue
        text = _ratchet.read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        finder = _Finder()
        finder.visit(tree)
        source = text.splitlines()
        for const in finder.found:
            line = const.lineno
            text_at = source[line - 1].strip() if line <= len(source) else ""
            hits.append(Hit(path=py, line=line, literal=const.value, key=f"{rel}:{line}:{const.value}", source=text_at))
    return sorted(hits, key=lambda h: (h.path, h.line, h.literal))


def _scan() -> list[Hit]:
    return scan_tree(SRC_ROOT)


def violation_key(hit: Hit) -> str:
    return hit.key


def describe(hit: Hit) -> str:
    return f"{hit.key}: {hit.source}"


def write_baseline(path: Path = BASELINE_PATH) -> int:
    header = (
        "# Grandfathered bare vocabulary literals (run state, job status, exit\n"
        "# reason, severity, grade, file-done status, dimension state, provider)\n"
        "# in comparisons, membership tests, match cases and status=/state=/\n"
        "# severity=/grade= arguments. The fix is the StrEnum member from the\n"
        "# vocabulary's home module. Burn to zero; never add.\n"
        "# Regenerate intentionally: python tools/check_vocab_literals.py --update-baseline\n"
    )
    return _ratchet.write_baseline(path, header, sorted({violation_key(h) for h in _scan()}))


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_vocab_literals.py [--update-baseline]`."""
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_vocab_literals.py",
        noun="vocabulary-literal",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=describe,
    ))


if __name__ == "__main__":
    sys.exit(main())
