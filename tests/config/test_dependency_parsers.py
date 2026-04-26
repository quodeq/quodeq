"""Unit tests for structured manifest parsers.

The corpus in ``test_discipline_corpus.py`` exercises happy paths through the
full ``DisciplineRegistry``. These tests cover edge cases — malformed input,
manifest dialects, name normalization — directly against the parser functions.
"""
from __future__ import annotations

import pytest

from quodeq.config._dependency_parsers import (
    has_cargo_dependency,
    has_composer_dependency,
    has_go_mod_module,
    has_package_json_dependency,
    has_pyproject_dependency,
    has_requirements_txt_dependency,
)


# --- pyproject.toml ----------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    # PEP 621 modern.
    ('[project]\nname="x"\ndependencies=["django>=4"]\n', "django", True),
    ('[project]\nname="x"\ndependencies=["flask==3"]\n', "django", False),
    # Optional-deps.
    (
        '[project]\nname="x"\n[project.optional-dependencies]\ndev=["pytest"]\n',
        "pytest", True,
    ),
    # Poetry.
    (
        '[tool.poetry]\nname="x"\n[tool.poetry.dependencies]\ndjango="^4"\n',
        "django", True,
    ),
    (
        '[tool.poetry]\nname="x"\n[tool.poetry.group.dev.dependencies]\npytest="^8"\n',
        "pytest", True,
    ),
    # PEP 735 dependency-groups.
    ('[dependency-groups]\ndev=["pytest"]\n', "pytest", True),
    # Comments must not match.
    ('# we used to depend on django\n[project]\nname="x"\ndependencies=["flask"]\n', "django", False),
    # Description text must not match.
    ('[project]\nname="x"\ndescription="A django-style framework"\ndependencies=["flask"]\n', "django", False),
    # Extras stripped: uvicorn[standard]==0.30 → uvicorn.
    ('[project]\nname="x"\ndependencies=["uvicorn[standard]==0.30"]\n', "uvicorn", True),
    # PEP 503 normalization: hyphens, underscores, dots all equivalent.
    ('[project]\nname="x"\ndependencies=["python-dateutil"]\n', "python_dateutil", True),
    # Case-insensitive.
    ('[project]\nname="x"\ndependencies=["Django>=4"]\n', "django", True),
    # django-stubs must NOT match django.
    ('[project]\nname="x"\ndependencies=["django-stubs"]\n', "django", False),
])
def test_pyproject(body: str, needle: str, expected: bool) -> None:
    assert has_pyproject_dependency(body, needle) is expected


def test_pyproject_malformed_returns_false() -> None:
    assert has_pyproject_dependency("this is not valid TOML [[[", "django") is False


# --- requirements.txt --------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    ("django>=4\n", "django", True),
    ("# comment line\nflask\n", "django", False),
    ("django>=4 # inline comment\n", "django", True),
    ("-r other.txt\nflask\n", "flask", True),
    ("--extra-index-url https://example.com\nflask\n", "flask", True),
    ("django-stubs\n", "django", False),  # exact name match
    ("Django==4.2\n", "django", True),  # case-insensitive
    ("python-dateutil\n", "python_dateutil", True),  # PEP 503 normalize
])
def test_requirements_txt(body: str, needle: str, expected: bool) -> None:
    assert has_requirements_txt_dependency(body, needle) is expected


# --- package.json ------------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    ('{"dependencies":{"react":"^18"}}', "react", True),
    ('{"devDependencies":{"react":"^18"}}', "react", True),
    ('{"peerDependencies":{"react":"^18"}}', "react", True),
    ('{"dependencies":{"preact":"^10"}}', "react", False),  # naive substring would FP
    ('{"dependencies":{"react-dom":"^18"}}', "react", False),  # exact name only
    ('{"description":"a react app","dependencies":{"vue":"^3"}}', "react", False),
    ('{"bundledDependencies":["react"]}', "react", True),
    ('{"dependencies":{"React":"^18"}}', "react", True),  # case-insensitive
])
def test_package_json(body: str, needle: str, expected: bool) -> None:
    assert has_package_json_dependency(body, needle) is expected


def test_package_json_malformed_returns_false() -> None:
    assert has_package_json_dependency("not json {{{", "react") is False


# --- Cargo.toml --------------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    ('[dependencies]\nactix-web = "4"\n', "actix-web", True),
    ('[dev-dependencies]\nmockall = "0.11"\n', "mockall", True),
    ('[build-dependencies]\ncc = "1.0"\n', "cc", True),
    (
        '[workspace]\n[workspace.dependencies]\nserde = "1"\n',
        "serde", True,
    ),
    (
        '[target."cfg(unix)".dependencies]\nlibc = "0.2"\n',
        "libc", True,
    ),
    ('[dependencies]\nactix-web-extras = "4"\n', "actix-web", False),  # exact key only
])
def test_cargo(body: str, needle: str, expected: bool) -> None:
    assert has_cargo_dependency(body, needle) is expected


# --- go.mod ------------------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    (
        "module x\ngo 1.22\nrequire github.com/gin-gonic/gin v1.9.0\n",
        "github.com/gin-gonic/gin", True,
    ),
    (
        "module x\ngo 1.22\n"
        "require (\n"
        "  github.com/gin-gonic/gin v1.9.0\n"
        "  github.com/stretchr/testify v1.8.0\n"
        ")\n",
        "github.com/gin-gonic/gin", True,
    ),
    # Versioned suffix: foo/v2 should match needle ``foo``.
    (
        "module x\nrequire github.com/gin-gonic/gin/v2 v2.0.0\n",
        "github.com/gin-gonic/gin", True,
    ),
    # Different module path: gofiber must not match gin.
    (
        "module x\nrequire github.com/gofiber/fiber/v2 v2.0.0\n",
        "github.com/gin-gonic/gin", False,
    ),
    # Module name appearing in a comment must not match.
    (
        "// migrating off github.com/gin-gonic/gin\n"
        "module x\nrequire github.com/gofiber/fiber v2 v2.0.0\n",
        "github.com/gin-gonic/gin", False,
    ),
])
def test_go_mod(body: str, needle: str, expected: bool) -> None:
    assert has_go_mod_module(body, needle) is expected


# --- composer.json -----------------------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    ('{"require":{"laravel/framework":"^10"}}', "laravel/framework", True),
    ('{"require-dev":{"phpunit/phpunit":"^10"}}', "phpunit/phpunit", True),
    ('{"require":{"symfony/console":"^7"}}', "laravel/framework", False),
])
def test_composer(body: str, needle: str, expected: bool) -> None:
    assert has_composer_dependency(body, needle) is expected
