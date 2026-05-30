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
_ALLOWLIST: set[str] = {
    # write_text() opener on its own line; encoding="utf-8" is passed on the
    # following continuation line. The call IS UTF-8-safe; the line-based
    # scanner just can't see a kwarg that lives on a different physical line.
    "analysis/_dim_estimates.py:70",
}


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
