"""Structured matchers for known dependency manifest formats.

Each matcher takes the raw file contents and a ``needle`` (the value of
``detect_contains`` from a discipline rule) and returns whether the manifest
declares that dependency. This replaces a naive substring match against the
raw text, which produced false positives in two classes:

* "preact" containing the substring "react" matched ``frontend_react``.
* The string "django" appearing in a comment of a ``pyproject.toml`` triggered
  ``python_django`` even when no Django dependency was declared.

For files we don't know how to parse, ``DisciplineRegistry`` falls back to the
existing substring behaviour — see ``_discipline_detection.py``.

Python (pyproject.toml, requirements.txt) matchers live in
``_dependency_parsers_python.py``; package.json/Cargo.toml/go.mod/
composer.json/pom.xml/Gradle matchers live in
``_dependency_parsers_compiled.py`` — both split out to keep this module
under the size ratchet's 300-line cap. All ``has_*`` names stay re-exported
from here.
"""
from __future__ import annotations

import re
import tomllib
from typing import Callable

from quodeq.config._dependency_parsers_python import (  # noqa: F401 - re-export
    has_pyproject_dependency,
    has_requirements_txt_dependency,
)
from quodeq.config._dependency_parsers_compiled import (  # noqa: F401 - re-export
    has_cargo_dependency,
    has_composer_dependency,
    has_go_mod_module,
    has_gradle_dependency,
    has_package_json_dependency,
    has_pom_xml_dependency,
)

# --- Gemfile (Ruby DSL) ------------------------------------------------------


_GEMFILE_GEM = re.compile(r"""^\s*gem\s+["']([^"']+)["']""", re.MULTILINE)


def _strip_hash_comments(content: str) -> str:
    """Remove ``#``-style line comments, preserving the rest of each line."""
    out: list[str] = []
    for line in content.splitlines():
        idx = line.find("#")
        out.append(line[:idx] if idx >= 0 else line)
    return "\n".join(out)


def _gemfile_gems(content: str) -> set[str]:
    body = _strip_hash_comments(content)
    return {m.group(1).lower() for m in _GEMFILE_GEM.finditer(body)}


def has_gemfile_gem(content: str, needle: str) -> bool:
    """Match exact gem names declared via ``gem "name"`` lines.

    A Gemfile mentioning ``rails`` only in a comment, or declaring a derived
    gem like ``rails-controller-testing``, no longer matches a needle of
    ``rails``. The match is exact against the first argument of ``gem "..."``.
    """
    return needle.strip().lower() in _gemfile_gems(content)


# --- mix.exs (Elixir) --------------------------------------------------------


_MIX_DEP = re.compile(r"\{:(\w+)\s*,")


def _mix_deps(content: str) -> set[str]:
    body = _strip_hash_comments(content)
    return {m.group(1).lower() for m in _MIX_DEP.finditer(body)}


def has_mix_dep(content: str, needle: str) -> bool:
    """Match dep atoms declared in mix.exs as ``{:name, ...}`` tuples.

    A mix.exs with ``# was using phoenix`` in a comment but no actual phoenix
    dep no longer matches needle ``phoenix``.
    """
    return needle.strip().lower() in _mix_deps(content)


# --- pubspec.yaml (Dart) -----------------------------------------------------


def _pubspec_deps(content: str) -> set[str]:
    """First-level keys under ``dependencies:`` / ``dev_dependencies:``.

    Hand-rolled rather than pulled in via PyYAML — pubspec layout is shallow,
    consistent, and we only need top-level keys under those two blocks.
    """
    deps: set[str] = set()
    in_block = False
    block_indent = -1
    for raw in content.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)
        if indent == 0:
            in_block = stripped.startswith(("dependencies:", "dev_dependencies:", "dependency_overrides:"))
            block_indent = -1
            continue
        if not in_block:
            continue
        if block_indent == -1:
            block_indent = indent
        if indent != block_indent:
            continue  # nested key, e.g. ``sdk: flutter`` under a dep — skip
        if ":" in stripped:
            key = stripped.split(":", 1)[0].strip()
            if key:
                deps.add(key.lower())
    return deps


def has_pubspec_dependency(content: str, needle: str) -> bool:
    """Match top-level keys in pubspec.yaml's dependency blocks.

    A description containing ``flutter`` no longer matches; only an actual
    ``flutter:`` key under ``dependencies:`` / ``dev_dependencies:`` does.
    """
    return needle.strip().lower() in _pubspec_deps(content)


# --- Project.toml (Julia) ----------------------------------------------------


def _julia_deps(content: str) -> set[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return set()
    names: set[str] = set()
    for key in ("deps", "weakdeps", "extras"):
        v = data.get(key)
        if isinstance(v, dict):
            names.update(k.lower() for k in v if isinstance(k, str))
    return names


def has_julia_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _julia_deps(content)


# --- dispatch ----------------------------------------------------------------


StructuredMatcher = Callable[[str, str], bool]

STRUCTURED_MATCHERS: dict[str, StructuredMatcher] = {
    "pyproject.toml": has_pyproject_dependency,
    "requirements.txt": has_requirements_txt_dependency,
    "package.json": has_package_json_dependency,
    "Cargo.toml": has_cargo_dependency,
    "go.mod": has_go_mod_module,
    "composer.json": has_composer_dependency,
    "pom.xml": has_pom_xml_dependency,
    "build.gradle": has_gradle_dependency,
    "build.gradle.kts": has_gradle_dependency,
    "Gemfile": has_gemfile_gem,
    "mix.exs": has_mix_dep,
    "pubspec.yaml": has_pubspec_dependency,
    "Project.toml": has_julia_dependency,
}


def get_structured_matcher(filename: str) -> StructuredMatcher | None:
    """Return a structured matcher for *filename*, or ``None`` for substring fallback."""
    return STRUCTURED_MATCHERS.get(filename)
