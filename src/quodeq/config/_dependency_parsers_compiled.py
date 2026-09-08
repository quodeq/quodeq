"""Structured matchers for package.json, Cargo.toml, go.mod, composer.json,
pom.xml (Maven), and Gradle build files.

Split from ``_dependency_parsers.py`` to keep that file under the size
ratchet's 300-line cap. All ``has_*`` names stay re-exported from there.
"""
from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from functools import lru_cache

# Same bound as ``_dependency_parsers._PARSE_CACHE_MAX`` (that module imports
# from here, so the constant cannot come from it): parse each manifest text
# once, not once per discipline rule that probes it.
_PARSE_CACHE_MAX = 64

# --- package.json ------------------------------------------------------------


_PACKAGE_JSON_DEP_KEYS = (
    "dependencies", "devDependencies", "peerDependencies",
    "optionalDependencies", "bundledDependencies", "bundleDependencies",
)


@lru_cache(maxsize=_PARSE_CACHE_MAX)
def _package_json_names(content: str) -> frozenset[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return frozenset()
    if not isinstance(data, dict):
        return frozenset()
    names: set[str] = set()
    for key in _PACKAGE_JSON_DEP_KEYS:
        v = data.get(key)
        if isinstance(v, dict):
            names.update(k.lower() for k in v if isinstance(k, str))
        elif isinstance(v, list):  # bundledDependencies is a list of strings
            names.update(s.lower() for s in v if isinstance(s, str))
    return frozenset(names)


def has_package_json_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _package_json_names(content)


# --- Cargo.toml --------------------------------------------------------------


@lru_cache(maxsize=_PARSE_CACHE_MAX)
def _cargo_dep_names(content: str) -> frozenset[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return frozenset()
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
    return frozenset(names)


def has_cargo_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _cargo_dep_names(content)


# --- go.mod ------------------------------------------------------------------


@lru_cache(maxsize=_PARSE_CACHE_MAX)
def _go_mod_modules(content: str) -> frozenset[str]:
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
    return frozenset(modules)


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


@lru_cache(maxsize=_PARSE_CACHE_MAX)
def _composer_dep_names(content: str) -> frozenset[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return frozenset()
    if not isinstance(data, dict):
        return frozenset()
    names: set[str] = set()
    for key in ("require", "require-dev"):
        v = data.get(key)
        if isinstance(v, dict):
            names.update(k.lower() for k in v if isinstance(k, str))
    return frozenset(names)


def has_composer_dependency(content: str, needle: str) -> bool:
    return needle.strip().lower() in _composer_dep_names(content)


# --- pom.xml (Maven) ---------------------------------------------------------


@lru_cache(maxsize=_PARSE_CACHE_MAX)
def _pom_coords(content: str) -> frozenset[str]:
    """Return all groupId / artifactId text values declared in *content*.

    Captures dependencies, parent coords, plugins, and BOM imports — anywhere a
    ``<groupId>`` or ``<artifactId>`` element appears. Commentary and free text
    in ``<description>`` / ``<comment>`` are not collected.
    """
    # Guard against XML entity-expansion (billion-laughs / XXE) attacks:
    # reject DOCTYPE and ENTITY declarations before parsing.
    if re.search(r"<!(DOCTYPE|ENTITY)", content, re.IGNORECASE):
        return frozenset()
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return frozenset()
    coords: set[str] = set()
    for elem in root.iter():
        # Strip default Maven namespace if present (``{http://maven.apache.org/POM/4.0.0}groupId``).
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag in ("groupId", "artifactId") and elem.text:
            coords.add(elem.text.strip())
    return frozenset(coords)


def has_pom_xml_dependency(content: str, needle: str) -> bool:
    """Substring-match *needle* against extracted Maven coordinates.

    Substring (not exact) because rule needles like ``spring-boot`` must match
    artifactIds like ``spring-boot-starter-web``. Description / comment text is
    excluded by construction — only ``<groupId>`` / ``<artifactId>`` are
    considered, so a ``<description>migrating off spring-boot</description>``
    no longer triggers a false match.
    """
    needle_low = needle.strip().lower()
    if not needle_low:
        return True
    return any(needle_low in c.lower() for c in _pom_coords(content))


# --- Gradle (Groovy / Kotlin DSL) -------------------------------------------


_GRADLE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_GRADLE_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_gradle_comments(content: str) -> str:
    return _GRADLE_LINE_COMMENT.sub("", _GRADLE_BLOCK_COMMENT.sub("", content))


@lru_cache(maxsize=_PARSE_CACHE_MAX)
def _gradle_searchable(content: str) -> str:
    """Comment-stripped, lowercased text the substring probe runs against.

    Gradle has no name set to extract (see ``has_gradle_dependency``), so the
    memoized unit is the searchable text rather than a frozenset of names.
    """
    return _strip_gradle_comments(content).lower()


def has_gradle_dependency(content: str, needle: str) -> bool:
    """Substring-match against build.gradle / build.gradle.kts with comments stripped.

    Real Gradle parsing requires a JVM; a comment-aware substring is the best
    we can do without one. Strips ``//`` line and ``/* */`` block comments first
    so a ``// migrating off spring-boot`` line no longer triggers a match.
    Coordinates inside string literals (the actual dep declarations) survive.
    """
    needle_low = needle.strip().lower()
    if not needle_low:
        return True
    return needle_low in _gradle_searchable(content)
