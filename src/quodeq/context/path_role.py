"""Classify a file path into a role (prod, test, fixture, packaging, ...).

The role is a coarse signal the rest of the pipeline uses to downweight
findings in non-production paths. Rules are language-agnostic globs so the
classifier behaves the same for Python, JS/TS, Go, Rust, Swift, Java, etc.

Matching is glob-style with three wildcards:

* ``**`` matches any number of path segments (including none).
* ``*``  matches any character except ``/``.
* ``?``  matches a single character except ``/``.

The first matching pattern wins, so more specific patterns are listed
first (e.g. ``tests/fixtures/**`` before ``tests/**``).
"""
from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache


class Role(str, Enum):
    """Coarse classification of a file's purpose in the project."""

    PROD = "prod"
    TEST = "test"
    TEST_FIXTURE = "test_fixture"
    BUILD = "build"
    PACKAGING = "packaging"
    TOOL = "tool"
    DOC = "doc"
    CONFIG = "config"


NON_PROD_ROLES: frozenset[Role] = frozenset({
    Role.TEST, Role.TEST_FIXTURE, Role.BUILD, Role.PACKAGING,
    Role.TOOL, Role.DOC, Role.CONFIG,
})


_DEFAULT_RULES: tuple[tuple[str, Role], ...] = (
    # Fixtures must come before tests/** so they classify as TEST_FIXTURE.
    ("tests/fixtures/**", Role.TEST_FIXTURE),
    ("**/fixtures/**", Role.TEST_FIXTURE),
    ("**/__fixtures__/**", Role.TEST_FIXTURE),
    ("**/testdata/**", Role.TEST_FIXTURE),
    # Test code (multiple language conventions).
    ("tests/**", Role.TEST),
    ("test/**", Role.TEST),
    ("**/__tests__/**", Role.TEST),
    ("**/spec/**", Role.TEST),
    ("**/specs/**", Role.TEST),
    ("**/test_*.py", Role.TEST),
    ("**/*_test.py", Role.TEST),
    ("**/*_test.go", Role.TEST),
    ("**/*.test.js", Role.TEST),
    ("**/*.test.jsx", Role.TEST),
    ("**/*.test.ts", Role.TEST),
    ("**/*.test.tsx", Role.TEST),
    ("**/*.spec.js", Role.TEST),
    ("**/*.spec.jsx", Role.TEST),
    ("**/*.spec.ts", Role.TEST),
    ("**/*.spec.tsx", Role.TEST),
    ("**/*Test.java", Role.TEST),
    ("**/*Tests.java", Role.TEST),
    ("**/*Spec.kt", Role.TEST),
    ("**/*Tests.swift", Role.TEST),
    # Packaging / CI.
    ("packaging/**", Role.PACKAGING),
    ("**/Dockerfile", Role.PACKAGING),
    ("**/Dockerfile.*", Role.PACKAGING),
    (".github/**", Role.PACKAGING),
    (".gitlab/**", Role.PACKAGING),
    # Build output / artifacts.
    ("build/**", Role.BUILD),
    ("dist/**", Role.BUILD),
    ("target/**", Role.BUILD),
    ("out/**", Role.BUILD),
    # Tools / scripts.
    ("tools/**", Role.TOOL),
    ("scripts/**", Role.TOOL),
    ("bin/**", Role.TOOL),
    # Docs.
    ("docs/**", Role.DOC),
    ("doc/**", Role.DOC),
    ("**/*.md", Role.DOC),
    ("**/*.rst", Role.DOC),
    # Config (catch-all by extension).
    ("**/*.toml", Role.CONFIG),
    ("**/*.yaml", Role.CONFIG),
    ("**/*.yml", Role.CONFIG),
    ("**/*.ini", Role.CONFIG),
    ("**/*.cfg", Role.CONFIG),
    ("**/*.json", Role.CONFIG),
)


@lru_cache(maxsize=None)
def _compile(pattern: str) -> re.Pattern[str]:
    """Translate a path glob to an anchored regex.

    Cached because every project re-uses the same default rule set across
    thousands of findings; recompiling per call would be wasteful.
    """
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # `**/` — zero or more directory segments.
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                else:
                    out.append(".*")
                    i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c in r".+()[]{}|^$\\":
            out.append("\\" + c)
            i += 1
        else:
            out.append(c)
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _normalize(file_path: str) -> str:
    p = file_path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def path_role(file_path: str | None) -> Role:
    """Classify *file_path* against the default rule table.

    Empty / falsy paths fall through as ``PROD`` (the safe default: do not
    downweight when we have no evidence). The first matching rule wins.
    """
    if not file_path:
        return Role.PROD
    norm = _normalize(file_path)
    if not norm:
        return Role.PROD
    for pattern, role in _DEFAULT_RULES:
        if _compile(pattern).match(norm):
            return role
    return Role.PROD
