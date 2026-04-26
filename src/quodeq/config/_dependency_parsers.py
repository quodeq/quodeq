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
"""
from __future__ import annotations

import json
import re
import tomllib
from typing import Callable

# PEP 503: package names are case-insensitive and ``[-_.]+`` normalize to ``-``.
_PEP503_SEP = re.compile(r"[-_.]+")


def _normalize_pep503(name: str) -> str:
    return _PEP503_SEP.sub("-", name).strip().lower()


def _parse_pep508_name(spec: str) -> str:
    """Extract the package name from a PEP 508 requirement string.

    Handles version specifiers, extras, environment markers, and direct URLs:
    ``django>=4`` → ``django``; ``uvicorn[standard]==0.30`` → ``uvicorn``;
    ``foo @ git+https://...`` → ``foo``; ``bar; python_version<'3.10'`` → ``bar``.
    """
    name = spec.strip()
    if ";" in name:
        name = name.split(";", 1)[0].strip()
    if "[" in name:
        name = name.split("[", 1)[0].strip()
    # Order matters: longer operators before shorter (=== before ==, >= before >).
    for op in ("===", "==", ">=", "<=", "~=", "!=", ">", "<", "@", " ", "\t"):
        if op in name:
            name = name.split(op, 1)[0].strip()
    return _normalize_pep503(name)


def _names_from_list(items: object) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {_parse_pep508_name(s) for s in items if isinstance(s, str) and s.strip()}


def _names_from_dict_keys(items: object) -> set[str]:
    if not isinstance(items, dict):
        return set()
    return {_normalize_pep503(k) for k in items if isinstance(k, str)}


# --- pyproject.toml ----------------------------------------------------------


def _pyproject_dep_names(content: str) -> set[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return set()

    names: set[str] = set()
    project = data.get("project")
    if isinstance(project, dict):
        names |= _names_from_list(project.get("dependencies"))
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for v in optional.values():
                names |= _names_from_list(v)

    poetry = data.get("tool", {}).get("poetry") if isinstance(data.get("tool"), dict) else None
    if isinstance(poetry, dict):
        names |= _names_from_dict_keys(poetry.get("dependencies"))
        names |= _names_from_dict_keys(poetry.get("dev-dependencies"))
        groups = poetry.get("group")
        if isinstance(groups, dict):
            for g in groups.values():
                if isinstance(g, dict):
                    names |= _names_from_dict_keys(g.get("dependencies"))

    # PEP 735 dependency groups (used by uv and others).
    dep_groups = data.get("dependency-groups")
    if isinstance(dep_groups, dict):
        for v in dep_groups.values():
            names |= _names_from_list(v)

    return names


def has_pyproject_dependency(content: str, needle: str) -> bool:
    return _normalize_pep503(needle) in _pyproject_dep_names(content)


# --- requirements.txt --------------------------------------------------------


def _requirements_txt_names(content: str) -> set[str]:
    names: set[str] = set()
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # Skip pip directives (-r, -e, --extra-index-url, etc.).
        if line.startswith("-"):
            continue
        name = _parse_pep508_name(line)
        if name:
            names.add(name)
    return names


def has_requirements_txt_dependency(content: str, needle: str) -> bool:
    return _normalize_pep503(needle) in _requirements_txt_names(content)


# --- package.json ------------------------------------------------------------


_PACKAGE_JSON_DEP_KEYS = (
    "dependencies", "devDependencies", "peerDependencies",
    "optionalDependencies", "bundledDependencies", "bundleDependencies",
)


def _package_json_names(content: str) -> set[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    names: set[str] = set()
    for key in _PACKAGE_JSON_DEP_KEYS:
        v = data.get(key)
        if isinstance(v, dict):
            names.update(k.lower() for k in v if isinstance(k, str))
        elif isinstance(v, list):  # bundledDependencies is a list of strings
            names.update(s.lower() for s in v if isinstance(s, str))
    return names


def has_package_json_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _package_json_names(content)


# --- Cargo.toml --------------------------------------------------------------


def _cargo_dep_names(content: str) -> set[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return set()
    names: set[str] = set()
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        v = data.get(key)
        if isinstance(v, dict):
            names.update(k.lower() for k in v if isinstance(k, str))
    # Workspace dependencies: [workspace.dependencies]
    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        wdeps = workspace.get("dependencies")
        if isinstance(wdeps, dict):
            names.update(k.lower() for k in wdeps if isinstance(k, str))
    # Target-specific dependencies: [target."cfg(...)".dependencies]
    target = data.get("target")
    if isinstance(target, dict):
        for tcfg in target.values():
            if not isinstance(tcfg, dict):
                continue
            for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                v = tcfg.get(key)
                if isinstance(v, dict):
                    names.update(k.lower() for k in v if isinstance(k, str))
    return names


def has_cargo_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _cargo_dep_names(content)


# --- go.mod ------------------------------------------------------------------


def _go_mod_modules(content: str) -> set[str]:
    """Return the set of module paths declared in ``require`` directives."""
    modules: set[str] = set()
    in_block = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line.startswith(")"):
            in_block = False
            continue
        if line.startswith("require "):
            line = line[len("require "):].strip()
        elif not in_block:
            continue
        # Strip inline comments and parse the first whitespace-delimited token.
        line = line.split("//", 1)[0].strip()
        parts = line.split(None, 1)
        if parts:
            modules.add(parts[0])
    return modules


def has_go_mod_module(content: str, needle: str) -> bool:
    """Match a module path. ``foo/bar`` matches both ``foo/bar`` and ``foo/bar/v2``."""
    needle = needle.strip()
    if not needle:
        return True
    prefix = needle + "/"
    for mod in _go_mod_modules(content):
        if mod == needle or mod.startswith(prefix):
            return True
    return False


# --- composer.json -----------------------------------------------------------


def _composer_dep_names(content: str) -> set[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    names: set[str] = set()
    for key in ("require", "require-dev"):
        v = data.get(key)
        if isinstance(v, dict):
            names.update(k.lower() for k in v if isinstance(k, str))
    return names


def has_composer_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _composer_dep_names(content)


# --- dispatch ----------------------------------------------------------------


StructuredMatcher = Callable[[str, str], bool]

STRUCTURED_MATCHERS: dict[str, StructuredMatcher] = {
    "pyproject.toml": has_pyproject_dependency,
    "requirements.txt": has_requirements_txt_dependency,
    "package.json": has_package_json_dependency,
    "Cargo.toml": has_cargo_dependency,
    "go.mod": has_go_mod_module,
    "composer.json": has_composer_dependency,
}


def get_structured_matcher(filename: str) -> StructuredMatcher | None:
    """Return a structured matcher for *filename*, or ``None`` for substring fallback."""
    return STRUCTURED_MATCHERS.get(filename)
