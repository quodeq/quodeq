"""Path-based role classifier.

Returns one of: composition_root, test, generated, vendored, migration, other.
"""

from __future__ import annotations

import re

_COMPOSITION_ROOT_BASENAMES = frozenset({"app.py", "main.py", "cli.py", "__main__.py"})

_TEST_PATTERNS = (
    re.compile(r"(^|/)tests?(/|$)"),
    re.compile(r"(^|/)_?test_[^/]+\.py$"),
    re.compile(r"(^|/)[^/]*_test\.py$"),
)

_GENERATED_PATTERNS = (
    re.compile(r"_pb2(_grpc)?\.py$"),
    re.compile(r"\.generated\.[a-zA-Z]+$"),
)

_VENDORED_PATTERNS = (
    re.compile(r"(^|/)vendor(/|$)"),
    re.compile(r"(^|/)third_party(/|$)"),
    re.compile(r"(^|/)node_modules(/|$)"),
    re.compile(r"(^|/)\.venv(/|$)"),
)

_MIGRATION_PATTERNS = (
    re.compile(r"(^|/)migrations(/|$)"),
    re.compile(r"(^|/)alembic/versions(/|$)"),
)


def classify_path_role(path: str) -> str:
    """Classify a repo-relative path into a role label."""
    norm = path.replace("\\", "/")
    basename = norm.rsplit("/", 1)[-1]

    for pat in _VENDORED_PATTERNS:
        if pat.search(norm):
            return "vendored"
    for pat in _GENERATED_PATTERNS:
        if pat.search(norm):
            return "generated"
    for pat in _MIGRATION_PATTERNS:
        if pat.search(norm):
            return "migration"
    for pat in _TEST_PATTERNS:
        if pat.search(norm):
            return "test"
    if basename in _COMPOSITION_ROOT_BASENAMES:
        return "composition_root"
    return "other"
