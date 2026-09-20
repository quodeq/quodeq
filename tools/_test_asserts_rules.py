"""Counting assertions per test, in Python (`ast`) and in JS (tokenizer).

Split out of tools/check_test_asserts.py so the checker stays small: this
module owns the two counters and the tree walk; the checker owns the
baseline. A test over `MAX_ASSERTIONS` is asserting several behaviours at
once and should be split, one behaviour per test.
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import _ratchet

MAX_ASSERTIONS = 8

TESTS_DIRNAME = "tests"
UI_TESTS_ROOT = ("src", "quodeq", "ui", "src")
JS_TEST_SUFFIXES = (".test.js", ".test.jsx")

# `it(`, `test(`, `it.only(`, `test.each(`... -- the call that opens a test.
_JS_TEST_CALL = re.compile(r"(?:^|[^\w.$])(it|test)((?:\.\w+)*)\s*\(")
_JS_EXPECT = re.compile(r"(?:^|[^\w.$])expect\s*\(")
_JS_NAME = re.compile(r"\s*(['\"`])(.*?)\1", re.DOTALL)


@dataclass(frozen=True, slots=True)
class TestCase:
    """One test function and how many assertions it makes."""

    key: str
    name: str
    count: int
    line: int


def over_limit(cases: list[TestCase]) -> list[TestCase]:
    """Return the cases asserting more than `MAX_ASSERTIONS` times."""
    return [case for case in cases if case.count > MAX_ASSERTIONS]


def _is_function(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


def _raises_blocks(node: ast.AST) -> int:
    """Count `with pytest.raises(...)` items; each is one assertion."""
    total = 0
    for sub in ast.walk(node):
        if not isinstance(sub, (ast.With, ast.AsyncWith)):
            continue
        for item in sub.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            total += name == "raises"
    return total


def _assertion_count(node: ast.AST) -> int:
    """Assertions in a test body: `assert` statements plus raises blocks."""
    asserts = sum(isinstance(sub, ast.Assert) for sub in ast.walk(node))
    return asserts + _raises_blocks(node)


def _test_functions(tree: ast.Module):
    """Yield (prefix, function) for every `test_*` function and method."""
    for node in tree.body:
        if _is_function(node) and node.name.startswith("test_"):
            yield "", node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if _is_function(sub) and sub.name.startswith("test_"):
                    yield f"{node.name}.", sub


def python_tests(source: str, rel: str) -> list[TestCase]:
    """Return one `TestCase` per `test_*` function in *source*."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"warning: skipping {rel}: {e}", file=sys.stderr)
        return []
    return [
        TestCase(
            key=f"{rel}:{prefix}{fn.name}",
            name=f"{prefix}{fn.name}",
            count=_assertion_count(fn),
            line=fn.lineno,
        )
        for prefix, fn in _test_functions(tree)
    ]


def blank_noise(source: str) -> str:
    """Return *source* with comments and string bodies blanked out.

    Same length as the input (so offsets still line up), so brace matching
    and `expect(` counting never trip over a brace or the word "expect"
    inside a comment or a string.
    """
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        char = source[i]
        two = source[i:i + 2]
        if two == "//":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
        elif two == "/*":
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            for j in range(i, end):
                out[j] = " " if source[j] != "\n" else "\n"
            i = end
        elif char in "'\"`":
            i = _blank_string(source, out, i, char)
        else:
            i += 1
    return "".join(out)


def _blank_string(source: str, out: list[str], start: int, quote: str) -> int:
    """Blank the string literal opening at *start*; return the index after it."""
    i = start + 1
    while i < len(source):
        char = source[i]
        if char == "\\":
            for j in (i, i + 1):
                if j < len(source) and source[j] != "\n":
                    out[j] = " "
            i += 2
            continue
        if char == quote:
            return i + 1
        out[i] = " " if char != "\n" else "\n"
        i += 1
    return i


def _call_end(cleaned: str, open_paren: int) -> int:
    """Index just past the `)` that closes the call opening at *open_paren*."""
    depth = 0
    for i in range(open_paren, len(cleaned)):
        if cleaned[i] == "(":
            depth += 1
        elif cleaned[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(cleaned)


def js_tests(source: str, rel: str) -> list[TestCase]:
    """Return one `TestCase` per `it()`/`test()` call in a JS test file."""
    cleaned = blank_noise(source)
    cases: list[TestCase] = []
    for match in _JS_TEST_CALL.finditer(cleaned):
        open_paren = match.end() - 1
        end = _call_end(cleaned, open_paren)
        body = cleaned[open_paren + 1:end]
        name = _test_name(source, open_paren + 1) or f"line {source.count(chr(10), 0, open_paren) + 1}"
        cases.append(TestCase(
            key=f"{rel}:{name}",
            name=name,
            count=len(_JS_EXPECT.findall(body)),
            line=source.count("\n", 0, open_paren) + 1,
        ))
    return cases


def _test_name(source: str, after_paren: int) -> str:
    """The test's first string argument, read from the original source."""
    match = _JS_NAME.match(source, after_paren)
    return " ".join(match.group(2).split()) if match else ""


def _js_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.name.endswith(JS_TEST_SUFFIXES) and "node_modules" not in path.parts:
            yield path


def scan_tree(repo_root: Path) -> list[TestCase]:
    """Return every test in `tests/` and the UI test files, sorted by key."""
    cases: list[TestCase] = []
    tests_root = repo_root / TESTS_DIRNAME
    if tests_root.is_dir():
        for path in _ratchet.iter_python_files(tests_root):
            text = _ratchet.read_text(path)
            if text is not None:
                cases += python_tests(text, path.relative_to(repo_root).as_posix())
    ui_root = repo_root.joinpath(*UI_TESTS_ROOT)
    if ui_root.is_dir():
        for path in _js_files(ui_root):
            text = _ratchet.read_text(path)
            if text is not None:
                cases += js_tests(text, path.relative_to(repo_root).as_posix())
    return sorted(cases, key=lambda case: case.key)
