"""Per-ecosystem deployment-shape signal detectors.

Split from ``project_shape.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.context._project_shape_io import (
    _flat_dep_names, _matches_any, _read_json, _read_text, _read_toml, _strip_dep_spec,
)
from quodeq.context._project_shape_types import Deployment

_PY_WEB_FRAMEWORKS = (
    "flask", "fastapi", "django", "starlette", "aiohttp",
    "sanic", "tornado", "bottle", "falcon", "pyramid",
)
_PY_DESKTOP_HINTS = (
    "pyinstaller", "pywebview", "tkinter", "pyside6", "pyqt5", "pyqt6",
    "kivy", "wxpython", "toga", "dearpygui",
)

_JS_WEB_FRAMEWORKS = (
    "express", "fastify", "next", "nestjs", "@nestjs/core", "koa",
    "hapi", "@hapi/hapi", "restify", "hono",
)
_JS_DESKTOP_HINTS = (
    "electron", "@electron/remote", "tauri", "@tauri-apps/api",
    "neutralinojs", "nodegui",
)
_JS_MOBILE_HINTS = (
    "react-native", "expo", "@ionic/core", "nativescript",
)
_JS_UI_LIBS = ("react", "vue", "svelte", "preact", "@angular/core", "solid-js")


def _python_signals(repo: Path) -> tuple[Deployment | None, list[str], list[str]]:
    """Return ``(deployment_hint, web_frameworks, desktop_hints)`` from pyproject.

    A deployment hint is not only set when the manifest is unambiguous: when a
    manifest lists BOTH web and desktop dependencies, desktop wins outright
    (see the comment below) rather than the hint going unset. The caller
    still fuses hints across all manifests before settling on a verdict.
    """
    pyproject = _read_toml(repo / "pyproject.toml")
    if pyproject is None:
        return None, [], []
    project_raw = pyproject.get("project") or {}
    project = project_raw if isinstance(project_raw, dict) else {}
    # isinstance, not `or []`: a scalar `dependencies = 5` is valid TOML, so
    # every reader above succeeds and `list(5)` raised TypeError straight out
    # of detect_shape. Same guard the optional-dependencies branch already
    # uses -- a nonsense value drops that one signal, it does not fail a scan.
    deps_raw = project.get("dependencies")
    deps_list = deps_raw if isinstance(deps_raw, list) else []
    optional_deps = project.get("optional-dependencies") or {}
    optional_flat: list[str] = []
    if isinstance(optional_deps, dict):
        for group in optional_deps.values():
            if isinstance(group, list):
                optional_flat.extend(group)
    raw = deps_list + optional_flat
    names = [_strip_dep_spec(d).lower() for d in raw if isinstance(d, str)]
    web = _matches_any(names, _PY_WEB_FRAMEWORKS)
    desktop = _matches_any(names, _PY_DESKTOP_HINTS)
    # Desktop wins outright when both are present. A desktop app routinely
    # embeds a web framework for its own UI (pywebview + flask, Electron +
    # express); a hosted service does not pull in pywebview. Returning None
    # here made detect_shape report UNKNOWN, which disables every downstream
    # shape consumer -- see detect_shape's own priority comment.
    if desktop:
        return Deployment.DESKTOP, web, desktop
    if web:
        return Deployment.WEB_SERVICE, web, desktop
    return None, web, desktop


def _node_signals(
    repo: Path,
) -> tuple[Deployment | None, list[str], list[str], str | None]:
    pkg = _read_json(repo / "package.json")
    if pkg is None:
        return None, [], [], None
    deps = _flat_dep_names(
        pkg.get("dependencies"),
        pkg.get("devDependencies"),
        pkg.get("peerDependencies"),
    )
    web = _matches_any(deps, _JS_WEB_FRAMEWORKS)
    desktop = _matches_any(deps, _JS_DESKTOP_HINTS)
    mobile = _matches_any(deps, _JS_MOBILE_HINTS)
    ui = next((u for u in _JS_UI_LIBS if u.lower() in deps), None)
    if mobile:
        return Deployment.MOBILE, web, desktop, ui
    if desktop:
        return Deployment.DESKTOP, web, desktop, ui
    if web:
        return Deployment.WEB_SERVICE, web, desktop, ui
    return None, web, desktop, ui


def _rust_signals(repo: Path) -> Deployment | None:
    cargo = _read_toml(repo / "Cargo.toml")
    if cargo is None:
        return None
    package_raw = cargo.get("package") or {}
    package = package_raw if isinstance(package_raw, dict) else {}
    has_lib = (repo / "src" / "lib.rs").exists() or "lib" in cargo
    has_bin = (repo / "src" / "main.rs").exists() or bool(cargo.get("bin"))
    publish = package.get("publish")
    # Cargo's publish defaults to True; explicit False means private/CLI.
    publishable = publish is not False
    if has_lib and not has_bin and publishable:
        return Deployment.LIBRARY
    if has_bin and not has_lib:
        return Deployment.CLI
    return None


_GO_WEB_IMPORTS = (
    "net/http", "github.com/gin-gonic/gin", "github.com/gorilla/mux",
    "github.com/labstack/echo", "github.com/gofiber/fiber",
)


def _go_signals(repo: Path) -> Deployment | None:
    if not (repo / "go.mod").exists():
        return None
    main_go = repo / "main.go"
    if main_go.exists():
        text = _read_text(main_go) or ""
        if any(imp in text for imp in _GO_WEB_IMPORTS):
            return Deployment.WEB_SERVICE
        return Deployment.CLI
    return None


_LANG_MARKERS: tuple[tuple[str, str], ...] = (
    ("python", "pyproject.toml"),
    ("python", "setup.py"),
    ("javascript", "package.json"),
    ("rust", "Cargo.toml"),
    ("go", "go.mod"),
    ("java", "pom.xml"),
    ("kotlin", "build.gradle.kts"),
    ("swift", "Package.swift"),
    ("ruby", "Gemfile"),
    ("dart", "pubspec.yaml"),
    ("php", "composer.json"),
)


def _detect_runtime_langs(repo: Path) -> list[str]:
    seen: list[str] = []
    for lang, marker in _LANG_MARKERS:
        if (repo / marker).exists() and lang not in seen:
            seen.append(lang)
    return seen
