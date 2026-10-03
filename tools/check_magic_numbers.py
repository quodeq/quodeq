#!/usr/bin/env python3
"""Magic-number ratchet: bare numeric literals the code passes, returns or compares.

Three rules over src/ (maintainability M-MDF-1, eval tags magic-number /
magic-value / magic-literal), src/quodeq/ui excluded (eslint owns it):

- A (argument): an int or float literal as a call positional argument, a
  keyword-argument value, or a function/lambda parameter default.
  ``sleep(0.25)`` should be ``sleep(POLL_INTERVAL_S)``.
- R (return): a literal returned, alone or as a display element
  (``return 5``, ``return (x, 5)``).
- C (compare): a literal operand of a comparison (``if n > 50``).

A literal inside a tuple, list, set or dict display counts as the display's
position: ``f([5, 10])`` flags both under A. ``-5`` is one literal, keyed
``-5``.

Not flagged: 0, 1, -1, 2 and -2 (and their float twins, ``0.0 == 0``);
bools; module- and class-level assignments (constant definitions, displays
and calls inside them included); anything under an arithmetic operator
(``x * 1000``, ``n // 2``, ``f(a + 5)``); subscripts and slices; arguments
of ``range``, ``enumerate``, ``round``, ``min``, ``max``, ``abs``, ``pow``,
``divmod``, ``zip``, ``sorted``, ``int``, ``float``, ``str``,
``HTTPStatus`` and ``exit``/``sys.exit``; octal literals (``0o600`` file
modes); annotations; f-strings, format specs included.

Keys are ``relpath:rule:literal`` (literal is ``repr(value)``) with no line
number: edits do not churn the baseline, and the end state is an empty
baseline. Regenerate intentionally:
    python tools/check_magic_numbers.py --update-baseline
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
BASELINE_PATH = REPO_ROOT / "tools" / "magic_numbers_baseline.txt"

EXCLUDE_PREFIXES = ("quodeq/ui/",)  # the UI tree has its own eslint gate
EXEMPT_VALUES = frozenset({0, 1, -1, 2, -2})  # identity, sign, halving: no name adds meaning
EXEMPT_BUILTINS = frozenset({
    "range", "enumerate", "round", "min", "max", "abs", "pow", "divmod",
    "zip", "sorted", "int", "float", "str", "HTTPStatus", "exit",
})
EXEMPT_ATTR_CALLS = frozenset({"HTTPStatus", "exit"})  # http.HTTPStatus(...), sys.exit(...)
OCTAL_PREFIXES = ("0o", "0O")
RULE_ARGUMENT = "A"
RULE_RETURN = "R"
RULE_COMPARE = "C"


@dataclass(frozen=True, slots=True)
class Hit:
    path: Path
    line: int
    rule: str
    literal: str
    key: str
    source: str


def _number(node: ast.AST) -> int | float | None:
    """The numeric value *node* spells (``5``, ``-5``, ``+0.5``), else None."""
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return sign * node.value
    return None


def _call_name(call: ast.Call) -> str:
    """The builtin a call exempts its arguments under, or ""."""
    func = call.func
    if isinstance(func, ast.Name) and func.id in EXEMPT_BUILTINS:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in EXEMPT_ATTR_CALLS:
        return func.attr
    return ""


class _Finder(ast.NodeVisitor):
    """Collects (rule, node) candidates; `skip` holds ids of exempt subtrees."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.skip: set[int] = set()
        self.found: list[tuple[str, ast.AST, int | float]] = []
        self._depth = 0  # function nesting; 0 is module or class body

    def _exempt(self, *nodes: ast.AST | None) -> None:
        for node in nodes:
            if node is not None:
                for sub in ast.walk(node):
                    self.skip.add(id(sub))

    def _collect(self, rule: str, node: ast.AST | None) -> None:
        """Record the literal *node* is, or the literals its display holds."""
        if node is None:
            return
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for elt in node.elts:
                self._collect(rule, elt)
        elif isinstance(node, ast.Dict):
            for part in (*node.keys, *node.values):
                self._collect(rule, part)
        elif (value := _number(node)) is not None:
            self.found.append((rule, node, value))

    def _collect_defaults(self, args: ast.arguments) -> None:
        for default in (*args.defaults, *args.kw_defaults):
            self._collect(RULE_ARGUMENT, default)

    def visit_arg(self, node: ast.arg) -> None:
        self._exempt(node.annotation)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._exempt(node.returns)
        self._collect_defaults(node.args)
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._collect_defaults(node.args)
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._depth == 0:
            self._exempt(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._exempt(node.annotation)
        if self._depth == 0:
            self._exempt(node.value)
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self._exempt(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self._exempt(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._exempt(node.slice)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node):
            self._exempt(*node.args, *(kw.value for kw in node.keywords))
        for arg in node.args:
            self._collect(RULE_ARGUMENT, arg)
        for kw in node.keywords:
            self._collect(RULE_ARGUMENT, kw.value)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        self._collect(RULE_RETURN, node.value)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for operand in (node.left, *node.comparators):
            self._collect(RULE_COMPARE, operand)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        segment = ast.get_source_segment(self.text, node) or ""
        if segment.startswith(OCTAL_PREFIXES):
            self._exempt(node)


def _leaf(node: ast.AST) -> ast.AST:
    """The Constant under a signed literal, so exemptions keyed on it apply."""
    return node.operand if isinstance(node, ast.UnaryOp) else node


def _scan_module(tree: ast.AST, text: str) -> list[tuple[str, ast.AST, int | float]]:
    """(rule, node, value) triples for one parsed module."""
    finder = _Finder(text)
    finder.visit(tree)
    return [
        (rule, node, value) for rule, node, value in finder.found
        if id(_leaf(node)) not in finder.skip and value not in EXEMPT_VALUES
    ]


def scan_tree(src_root: Path) -> list[Hit]:
    """Every rule-A, rule-R and rule-C hit under *src_root*, one per key."""
    hits: dict[str, Hit] = {}
    for py in _ratchet.iter_python_files(src_root):
        rel = py.relative_to(src_root).as_posix()
        if rel.startswith(EXCLUDE_PREFIXES):
            continue
        text = _ratchet.read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        lines = text.splitlines()
        for rule, node, value in _scan_module(tree, text):
            literal = repr(value)
            key = f"{rel}:{rule}:{literal}"
            if key not in hits:
                src = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                hits[key] = Hit(py, node.lineno, rule, literal, key, src)
    return sorted(hits.values(), key=lambda h: h.key)


def _scan() -> list[Hit]:
    return scan_tree(SRC_ROOT)


def violation_key(hit: Hit) -> str:
    return hit.key


def describe(hit: Hit) -> str:
    rel = hit.key.split(":", 1)[0]
    return f"{rel}:{hit.line} [{hit.rule}] {hit.literal}: {hit.source}"


def write_baseline(path: Path = BASELINE_PATH) -> int:
    header = (
        "# Grandfathered magic numbers: rule A (a bare number passed as an\n"
        "# argument or parameter default), rule R (returned) and rule C (compared\n"
        "# against). The fix is a named constant that carries meaning and unit.\n"
        "# Burn to zero; never add.\n"
        "# Regenerate intentionally: python tools/check_magic_numbers.py --update-baseline\n"
    )
    return _ratchet.write_baseline(path, header, [violation_key(h) for h in _scan()])


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_magic_numbers.py [--update-baseline]`."""
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_magic_numbers.py",
        noun="magic-number",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=describe,
    ))


if __name__ == "__main__":
    sys.exit(main())
