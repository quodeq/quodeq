"""Shared fixtures for tests/analysis/test_deterministic_checks_*.py siblings.

Split out of test_deterministic_checks.py.
"""
from __future__ import annotations

import json

import pytest

from quodeq.analysis.checks.runner import deterministic_judgments

STANDARD = {
    "id": "clean-architecture",
    "principles": [
        {
            "name": "Independence from Frameworks",
            "requirements": [{"id": "CLEA-FRM-01", "text": "no frameworks inside",
                              "check": "framework-imports"}],
        },
        {
            "name": "Dependency Rule",
            "requirements": [{"id": "CLEA-DEP-06", "text": "no transitive frameworks",
                              "check": "framework-imports"}],
        },
    ],
}


@pytest.fixture
def project(tmp_path):
    """A tiny layered project: domain -> utils -> flask."""
    for rel, body in (
        ("app/__init__.py", ""),
        ("app/domain/__init__.py", ""),
        ("app/domain/order.py", "from app.utils import text\n"),
        ("app/utils/__init__.py", ""),
        ("app/utils/text.py", "import flask\n"),
    ):
        path = tmp_path / "repo" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path / "repo"


@pytest.fixture
def compiled(tmp_path):
    def _write(standard, dimension="clean-architecture"):
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir(exist_ok=True)
        (compiled_dir / f"{dimension}.json").write_text(
            json.dumps(standard), encoding="utf-8")
        return compiled_dir
    return _write


SOURCES = ("app/domain/order.py", "app/utils/text.py", "app/utils/__init__.py")


def _judge(project, compiled_dir, dimension="clean-architecture"):
    return deterministic_judgments(
        root=project, source_files=SOURCES, dimension=dimension,
        compiled_dir=compiled_dir,
    )
