# tests/test_no_bare_text_io.py
"""Guard: text-mode file I/O must pin encoding (UTF-8) for Windows safety.

On Windows, Path.read_text()/write_text() and builtin open() default to the
locale code page (e.g. cp1252), not UTF-8. Non-ASCII content then mis-decodes
or raises UnicodeDecodeError at runtime, a bug class ASCII-only unit fixtures
never catch. Pass encoding= explicitly on every text-mode call.

This is a line-based scan. It also covers text-mode ``<receiver>.open(...)``
calls (e.g. ``Path.open("w")``), which share the same cp1252 default. Receivers
whose ``.open()`` is not a text-file open (fd-level ``os.open``, ``webbrowser``,
or binary/archive openers like ``gzip``/``tarfile``/``zipfile``) are excluded
via ``_NON_TEXT_OPEN``; binary-mode opens are exempted by ``_BINARY_MODE``.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "quodeq"

_READ_WRITE = re.compile(r"\.(read_text|write_text)\(")
_OPEN = re.compile(r"(?<![\w.])open\(")
_DOT_OPEN = re.compile(r"\.open\(")
_HAS_ENCODING = re.compile(r"encoding\s*=")
_BINARY_MODE = re.compile(r"""['"][rwax]{1,2}b\+?['"]""")

# .open() receivers that are NOT text-file opens (fd-level, URLs, or binary/archive).
_NON_TEXT_OPEN = (
    "os.open(",
    "webbrowser.open(",
    "gzip.open(",
    "tarfile.open(",
    "zipfile.",
    # zipfile.ZipFile.open() returns a binary stream (no encoding= concept).
    "zf.open(",
)

# Sites that legitimately cannot pin encoding (document the reason).
# Format: "src-relative/path.py:LINE"
_ALLOWLIST: set[str] = set()


def _offenders() -> list[str]:
    bad: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        rel = py.relative_to(SRC).as_posix()
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if f"{rel}:{i}" in _ALLOWLIST:
                continue
            if _HAS_ENCODING.search(line) or _BINARY_MODE.search(line):
                continue
            dot_open = _DOT_OPEN.search(line) and not any(
                token in line for token in _NON_TEXT_OPEN
            )
            if _READ_WRITE.search(line) or _OPEN.search(line) or dot_open:
                bad.append(f"{rel}:{i}: {line.strip()}")
    return bad


def test_no_bare_text_io() -> None:
    offenders = _offenders()
    assert not offenders, (
        f"{len(offenders)} text-I/O call(s) without explicit encoding "
        "(breaks on Windows cp1252). Pass encoding='utf-8':\n  "
        + "\n  ".join(offenders)
    )


# --- subprocess text=True / os.fdopen coverage (AST-based) -----------------
#
# subprocess.run/Popen(..., text=True) decodes child output with the locale
# code page on Windows, exactly like bare open(). The line-based scan above
# cannot catch it because the encoding= kwarg may sit on a different line of
# the same multi-line call, so this check parses the AST instead. os.fdopen
# in text mode shares the same default and is missed by the open() regex.

_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output", "check_call", "call"})

# Sites that legitimately cannot pin encoding (document the reason).
# Format: "src-relative/path.py:LINE"
_SUBPROCESS_ALLOWLIST: set[str] = set()


def _is_subprocess_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _SUBPROCESS_FUNCS
        and isinstance(func.value, ast.Name)
        and "subprocess" in func.value.id
    )


def _is_text_fdopen(node: ast.Call) -> bool:
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "fdopen"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    ):
        return False
    mode = "r"
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and "b" not in mode


def _subprocess_text_offenders() -> list[str]:
    bad: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        rel = py.relative_to(SRC).as_posix()
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if f"{rel}:{node.lineno}" in _SUBPROCESS_ALLOWLIST:
                continue
            kwargs = {kw.arg for kw in node.keywords if kw.arg}
            if "encoding" in kwargs:
                continue
            if _is_subprocess_call(node):
                wants_text = any(
                    kw.arg in ("text", "universal_newlines")
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in node.keywords
                )
                if wants_text:
                    bad.append(f"{rel}:{node.lineno}: subprocess {node.func.attr}(text=True)")
            elif _is_text_fdopen(node):
                bad.append(f"{rel}:{node.lineno}: os.fdopen() in text mode")
    return bad


def test_no_bare_subprocess_text() -> None:
    offenders = _subprocess_text_offenders()
    assert not offenders, (
        f"{len(offenders)} subprocess/fdopen call(s) decode text without explicit "
        "encoding (breaks on Windows cp1252). Pass encoding='utf-8':\n  "
        + "\n  ".join(offenders)
    )
