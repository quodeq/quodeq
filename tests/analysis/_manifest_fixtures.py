"""Shared fixtures for tests/analysis/test_manifest_*.py siblings.

Split out of test_manifest.py.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def detection() -> dict:
    return {
        "extensions": {
            ".py": "python",
            ".ts": "typescript",
            ".js": "javascript",
            ".java": "java",
        },
        "skip_dirs": ["node_modules", "__pycache__", ".git", "dist"],
        "config_files": {
            "pyproject.toml": "python",
            "tsconfig.json": "typescript",
        },
        "skip_patterns": ["*.min.js"],
    }
