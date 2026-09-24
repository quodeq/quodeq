#!/usr/bin/env python3
"""Magic-string ratchet: bare string literals the code branches on or repeats.

Two rules over src/ (maintainability M-MDF-1, eval tags magic-string /
magic-value / magic-literal):

- C (compare): a string literal in ``==``/``!=``, in the right operand of
  ``in``/``not in`` (tuple, list, set, ``set()``/``frozenset()`` argument), or
  a ``case`` value. ``s == "active"`` should be ``s == WorktreeStatus.ACTIVE``.
- R (repeat): the same literal three or more times in one module in value
  positions. Three copies of ``"status.json"`` should be one named constant.

Not flagged: literals with no letter or digit (separators such as ``", "``),
docstrings, f-string parts, log/print/raise message arguments, dict keys,
subscripts, keyword-argument values (``encoding="utf-8"`` names itself),
module- and class-level constant definitions, ``__name__ == "__main__"``,
and words owned by tools/check_vocab_literals.py (one gate per literal).

Keys are ``relpath:rule:literal`` with no line number: edits do not churn the
baseline, and the end state is an empty baseline. Regenerate intentionally:
    python tools/check_magic_strings.py --update-baseline
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ratchet  # noqa: E402
from check_vocab_literals import VOCAB_WORDS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
BASELINE_PATH = REPO_ROOT / "tools" / "magic_strings_baseline.txt"

REPEAT_THRESHOLD = 3  # a literal written this many times in one module needs a name
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})
MESSAGE_CALLS = frozenset({"print"})
KEY_METHODS = frozenset({"get", "pop", "setdefault"})
ATTR_CALLS = frozenset({"getattr", "hasattr", "setattr", "delattr"})  # the name argument is an attribute name
RULE_COMPARE = "C"
RULE_REPEAT = "R"


@dataclass(frozen=True, slots=True)
class Hit:
    path: Path
    line: int
    rule: str
    literal: str
    key: str
    source: str


def _is_text(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
        and any(ch.isalnum() for ch in node.value) and node.value not in VOCAB_WORDS
    )


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _members(node: ast.AST) -> list[ast.AST]:
    """The literals a membership right operand holds."""
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return list(node.elts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"} and node.args:
        return _members(node.args[0])
    return [node]


def _is_main_guard(node: ast.Compare) -> bool:
    return isinstance(node.left, ast.Name) and node.left.id == "__name__"


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


class _Finder(ast.NodeVisitor):
    """Collects rule-C constants and every value-position constant (for R)."""

    def __init__(self, skip: set[int]) -> None:
        self.skip = skip
        self.compared: list[ast.Constant] = []
        self.values: list[ast.Constant] = []
        self._depth = 0  # function nesting; 0 is module or class body

    def _exempt(self, *nodes: ast.AST) -> None:
        for node in nodes:
            for sub in ast.walk(node):
                self.skip.add(id(sub))

    def visit_arg(self, node: ast.arg) -> None:
        if node.annotation is not None:
            self._exempt(node.annotation)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.returns is not None:
            self._exempt(node.returns)
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._depth == 0:
            self._exempt(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._exempt(node.annotation)
        if self._depth == 0 and node.value is not None:
            self._exempt(node.value)
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self._exempt(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self._exempt(*(k for k in node.keys if k is not None))
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._exempt(node.slice)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if isinstance(node.value, ast.Constant):
            self._exempt(node.value)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if isinstance(node.exc, ast.Call):
            self._exempt(*node.exc.args)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in LOG_METHODS or name in MESSAGE_CALLS:
            self._exempt(*node.args)
        elif name in KEY_METHODS and isinstance(node.func, ast.Attribute) and node.args:
            self._exempt(node.args[0])
        elif name in ATTR_CALLS and isinstance(node.func, ast.Name) and len(node.args) >= 2:
            self._exempt(node.args[1])
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if not _is_main_guard(node):
            left = node.left
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    self.compared.extend(c for c in (left, right) if _is_text(c))
                elif isinstance(op, (ast.In, ast.NotIn)):
                    self.compared.extend(c for c in _members(right) if _is_text(c))
                left = right
        self.generic_visit(node)

    def visit_match_case(self, node: ast.match_case) -> None:
        for sub in ast.walk(node.pattern):
            if isinstance(sub, ast.MatchValue) and _is_text(sub.value):
                self.compared.append(sub.value)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if _is_text(node):
            self.values.append(node)


def _scan_module(tree: ast.AST) -> list[tuple[str, ast.Constant]]:
    """(rule, constant) pairs for one parsed module."""
    finder = _Finder(_docstring_ids(tree))
    finder.visit(tree)
    live = [c for c in finder.values if id(c) not in finder.skip]
    by_literal: dict[str, list[ast.Constant]] = defaultdict(list)
    for const in live:
        by_literal[const.value].append(const)
    found = [(RULE_COMPARE, c) for c in finder.compared if id(c) not in finder.skip]
    for consts in by_literal.values():
        if len(consts) >= REPEAT_THRESHOLD:
            found.append((RULE_REPEAT, consts[0]))
    return found


def scan_tree(src_root: Path) -> list[Hit]:
    """Every rule-C and rule-R hit under *src_root*, one per key."""
    hits: dict[str, Hit] = {}
    for py in _ratchet.iter_python_files(src_root):
        rel = py.relative_to(src_root).as_posix()
        text = _ratchet.read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        lines = text.splitlines()
        for rule, const in _scan_module(tree):
            key = f"{rel}:{rule}:{const.value}"
            if key not in hits:
                src = lines[const.lineno - 1].strip() if const.lineno <= len(lines) else ""
                hits[key] = Hit(py, const.lineno, rule, const.value, key, src)
    return sorted(hits.values(), key=lambda h: h.key)


def _scan() -> list[Hit]:
    return scan_tree(SRC_ROOT)


def violation_key(hit: Hit) -> str:
    return hit.key


def describe(hit: Hit) -> str:
    rel = hit.key.split(":", 1)[0]
    return f"{rel}:{hit.line} [{hit.rule}] {hit.literal!r}: {hit.source}"


def write_baseline(path: Path = BASELINE_PATH) -> int:
    header = (
        "# Grandfathered magic strings: rule C (a bare string the code compares\n"
        "# against) and rule R (the same string 3+ times in one module). The fix\n"
        "# is a named constant or an enum member. Burn to zero; never add.\n"
        "# Regenerate intentionally: python tools/check_magic_strings.py --update-baseline\n"
    )
    return _ratchet.write_baseline(path, header, [violation_key(h) for h in _scan()])


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_magic_strings.py [--update-baseline]`."""
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_magic_strings.py",
        noun="magic-string",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=describe,
    ))


if __name__ == "__main__":
    sys.exit(main())
