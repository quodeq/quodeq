#!/usr/bin/env python3
"""Vocabulary-literal ratchet: flag bare state/severity/grade strings in comparisons.

Closed vocabularies (run state, job status, exit reason, severity, grade,
file-done status, dimension state, provider, finding type) are StrEnums in one
home module each (HOME_MODULES). Writing one of their values as a bare string
where the
code branches on it -- `s == "running"`, `s in {"done", "failed"}`,
`case "cancelled":`, `status="done"`, `{"status": "done"}` -- or writes it
into a variable or attribute named for the vocabulary -- `self.status =
"done"`, `state = "running"` -- or reads it as the fallback of a
vocabulary-named key -- `d.get("state", "running")` -- is what this gate
flags (maintainability M-MDF-1, and the typo class nothing else catches).
A set/tuple/list literal holding two or more words of the same vocabulary
is flagged wherever it sits: `_TERMINAL = frozenset({"done", "failed"})` is
a hand-copied subset of the enum.
The fix is the enum member: `s == RunState.RUNNING`.

Not flagged: dict keys, the left operand of `in`/`not in` (`"error" in
payload` is a key test), f-strings, docstrings, log/message arguments, and
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
    "quodeq/core/types/finding_type.py",
})

# One word set per vocabulary. A word may belong to several (``done`` is a
# run state, a job status, an exit reason and a dimension state); the
# same-vocabulary collection rule counts per set.
VOCABULARIES: dict[str, frozenset[str]] = {
    "RunState": frozenset({
        "pending", "running", "finalizing", "done", "failed", "cancelled",
        # legacy spellings parse_run_state still reads
        "complete", "completed", "finished", "in_progress", "canceled", "error", "lost",
    }),
    "JobStatus": frozenset({"running", "done", "failed", "cancelled", "lost"}),
    "ExitReason": frozenset({
        "done", "time_limit", "deadline", "failure_streak", "cancelled", "error",
        "stale_detected", "stale_legacy_pid_dead", "stale_legacy_no_pid",
    }),
    "Severity": frozenset({"critical", "major", "minor"}),
    "Grade": frozenset({"Exemplary", "Good", "Adequate", "Poor", "Insufficient"}),
    "FileDoneStatus": frozenset({"ok", "error", "skipped"}),
    "DimState": frozenset({"pending", "running", "done", "incomplete"}),
    "Provider": frozenset({"claude", "codex", "gemini", "copilot", "ollama", "llamacpp", "openrouter", "custom"}),
    "FindingType": frozenset({"violation", "compliance"}),
}

VOCAB_WORDS = frozenset().union(*VOCABULARIES.values())

VOCAB_KEYWORDS = frozenset({"status", "state", "severity", "grade", "run_state", "exit_reason", "provider", "verdict"})


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


def _is_vocab_target(node: ast.AST) -> bool:
    """True for an assignment target named for one of the vocabularies."""
    if isinstance(node, ast.Name):
        return node.id in VOCAB_KEYWORDS
    if isinstance(node, ast.Attribute):
        return node.attr in VOCAB_KEYWORDS
    return False


def _assigned_constants(target: ast.AST, value: ast.AST | None) -> list[ast.Constant]:
    """The vocabulary constants *value* writes into a vocabulary-named target.

    A tuple target is paired with a tuple value element by element, so
    ``grade, other = "Poor", x`` reports only the grade.
    """
    if value is None:
        return []
    if isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, (ast.Tuple, ast.List)) and len(target.elts) == len(value.elts):
            return [c for t, v in zip(target.elts, value.elts) for c in _assigned_constants(t, v)]
        return _vocab_constants(value) if any(_is_vocab_target(t) for t in target.elts) else []
    return _vocab_constants(value) if _is_vocab_target(target) else []


def _same_vocab_constants(node: ast.Set | ast.Tuple | ast.List) -> list[ast.Constant]:
    """The elements of a collection literal that share a vocabulary with another element."""
    consts = [e for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value in VOCAB_WORDS]
    out: list[ast.Constant] = []
    for words in VOCABULARIES.values():
        members = [c for c in consts if c.value in words]
        if len(members) >= 2:  # noqa: PLR2004 -- "two or more" is the rule itself
            out.extend(members)
    return out


def _is_vocab_get(node: ast.Call) -> bool:
    """True for ``<x>.get("<vocab key>", <default>)``."""
    return (
        isinstance(node.func, ast.Attribute) and node.func.attr == "get"
        and len(node.args) >= 2  # noqa: PLR2004 -- key and default
        and isinstance(node.args[0], ast.Constant) and node.args[0].value in VOCAB_KEYWORDS
    )


class _Finder(ast.NodeVisitor):
    """Collects every vocabulary constant sitting in a branching or write position."""

    def __init__(self) -> None:
        self.found: list[ast.Constant] = []

    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left, *node.comparators]
        if isinstance(node.ops[0], (ast.In, ast.NotIn)):
            operands = operands[1:]  # `"error" in payload` tests a key, not a state
        for operand in operands:
            self.found.extend(_vocab_constants(operand))
        self.generic_visit(node)

    def visit_Set(self, node: ast.Set) -> None:
        self.found.extend(_same_vocab_constants(node))
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self.found.extend(_same_vocab_constants(node))
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self.found.extend(_same_vocab_constants(node))
        self.generic_visit(node)

    def visit_match_case(self, node: ast.match_case) -> None:
        self.found.extend(_match_constants(node.pattern))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg in VOCAB_KEYWORDS:
                self.found.extend(_vocab_constants(kw.value))
        if _is_vocab_get(node):
            self.found.extend(_vocab_constants(node.args[1]))
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value in VOCAB_KEYWORDS:
                self.found.extend(_vocab_constants(value))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self.found.extend(_assigned_constants(target, node.value))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.found.extend(_assigned_constants(node.target, node.value))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.found.extend(_assigned_constants(node.target, node.value))
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
        # A constant can match twice (a comparator that is also a same-vocab
        # collection); report it once.
        unique = {id(c): c for c in finder.found}.values()
        for const in unique:
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
        "# reason, severity, grade, file-done status, dimension state, provider,\n"
        "# finding type) in comparisons, membership tests, match cases and\n"
        "# status=/state=/severity=/grade=/verdict= arguments. The fix is the\n"
        "# StrEnum member from the vocabulary's home module. Burn to zero; never add.\n"
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
