"""Structured matchers for Python dependency manifests: pyproject.toml and
requirements.txt.

Split from ``_dependency_parsers.py`` to keep that file under the size
ratchet's 300-line cap. ``has_pyproject_dependency`` / ``has_requirements_txt_dependency``
stay re-exported from there. Moved verbatim.
"""
from __future__ import annotations

import re
import tomllib

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
