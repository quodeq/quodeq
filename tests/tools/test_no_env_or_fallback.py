"""Gate: no `env or os.environ` truthiness fallback anywhere in src/.

`env or os.environ` silently turns an injected empty mapping back into the
process environment, so a test that passes `env={}` to mean "no variables
set" gets the real environment instead. The correct spelling is
`os.environ if env is None else env`.

Marked xfail(strict) until PR 2 Task 2 rewrites the 47 remaining sites; it
flips to a plain test in that task.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PATTERN = re.compile(r"\bor\s+os\.environ\b")


@pytest.mark.xfail(strict=True, reason="PR 2 Task 2 removes the 47 sites")
def test_no_truthiness_fallback_to_process_env():
    root = Path(__file__).resolve().parents[2]
    hits = [
        f"{p.relative_to(root)}:{i}"
        for p in sorted((root / "src").rglob("*.py"))
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if PATTERN.search(line)
    ]
    assert hits == [], (
        "Use `os.environ if env is None else env`; `or` treats an injected "
        "empty mapping as unset:\n" + "\n".join(hits)
    )
