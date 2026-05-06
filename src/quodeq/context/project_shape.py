"""Detect a project's deployment shape from its manifest files.

Reads ``pyproject.toml``, ``package.json``, ``Cargo.toml``, ``go.mod`` and
similar at the repo root and produces a :class:`ProjectShape`. Detection is
language-agnostic: every check is a manifest pattern, never a code-level
assumption.

The shape is the single biggest source of false positives in the current
audit corpus (~40%) because the scanner defaults to "hosted multi-tenant
web service" assumptions on what is in fact a desktop / CLI / library.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class Deployment(str, Enum):
    DESKTOP = "desktop"
    CLI = "cli"
    WEB_SERVICE = "web_service"
    LIBRARY = "library"
    MOBILE = "mobile"
    EMBEDDED = "embedded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProjectShape:
    """Coarse classification of what a repository ships.

    Fields are populated best-effort from manifests; absent signals leave
    fields as their defaults (``UNKNOWN`` / empty list / ``None``). The
    finding pipeline reads ``deployment`` and ``is_single_user`` to decide
    whether hosted-service findings (concurrent callers, distributed state,
    blocking the request thread) deserve their default confidence.
    """

    deployment: Deployment = Deployment.UNKNOWN
    runtime_langs: list[str] = field(default_factory=list)
    web_frameworks: list[str] = field(default_factory=list)
    ui_lang: str | None = None
    is_single_user: bool = True

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["deployment"] = self.deployment.value
        return d


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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_toml(path: Path) -> dict[str, object] | None:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _read_json(path: Path) -> dict[str, object] | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _flat_dep_names(*sources: object) -> list[str]:
    out: list[str] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in src:
            out.append(str(key).lower())
    return out


def _matches_any(haystack: list[str], needles: tuple[str, ...]) -> list[str]:
    needle_set = {n.lower() for n in needles}
    return [n for n in haystack if n in needle_set]


def _python_signals(repo: Path) -> tuple[Deployment | None, list[str], list[str]]:
    """Return ``(deployment_hint, web_frameworks, desktop_hints)`` from pyproject.

    A deployment hint is only set when the manifest is unambiguous; the
    caller fuses signals across all manifests before settling on a verdict.
    """
    pyproject = _read_toml(repo / "pyproject.toml")
    if pyproject is None:
        return None, [], []
    project_raw = pyproject.get("project") or {}
    project = project_raw if isinstance(project_raw, dict) else {}
    deps_list = project.get("dependencies") or []
    optional_deps = project.get("optional-dependencies") or {}
    optional_flat: list[str] = []
    if isinstance(optional_deps, dict):
        for group in optional_deps.values():
            if isinstance(group, list):
                optional_flat.extend(group)
    raw = list(deps_list) + optional_flat
    names = [_strip_dep_spec(d).lower() for d in raw if isinstance(d, str)]
    web = _matches_any(names, _PY_WEB_FRAMEWORKS)
    desktop = _matches_any(names, _PY_DESKTOP_HINTS)
    if web and not desktop:
        return Deployment.WEB_SERVICE, web, desktop
    if desktop and not web:
        return Deployment.DESKTOP, web, desktop
    return None, web, desktop


_DEP_SPEC_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _strip_dep_spec(spec: str) -> str:
    """Reduce a PEP 508 spec like ``flask>=3.0`` to its bare name."""
    m = _DEP_SPEC_RE.match(spec.strip())
    return m.group(1) if m else spec.strip()


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


def detect_shape(repo_path: Path) -> ProjectShape:
    """Detect a :class:`ProjectShape` from manifests at *repo_path*.

    Falls back to ``Deployment.UNKNOWN`` whenever signals are absent or
    contradictory; callers must treat ``UNKNOWN`` as a no-op (no downweight,
    no prompt enrichment).
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        return ProjectShape()

    py_dep, py_web, _ = _python_signals(repo)
    js_dep, js_web, _, ui_lang = _node_signals(repo)
    rust_dep = _rust_signals(repo)
    go_dep = _go_signals(repo)

    # Priority: explicit desktop/mobile signals beat web signals beat library
    # beat cli, since desktop hints come from very specific dep names while
    # web hints can show up in dev dependencies of desktop apps.
    deployment = Deployment.UNKNOWN
    for candidate in (py_dep, js_dep, rust_dep, go_dep):
        if candidate is None:
            continue
        if candidate is Deployment.DESKTOP:
            deployment = Deployment.DESKTOP
            break
        if candidate is Deployment.MOBILE:
            deployment = Deployment.MOBILE
            break
    else:
        for candidate in (py_dep, js_dep, rust_dep, go_dep):
            if candidate is None:
                continue
            if deployment is Deployment.UNKNOWN:
                deployment = candidate

    web_frameworks = sorted({*py_web, *js_web})
    runtime_langs = _detect_runtime_langs(repo)
    is_single_user = deployment is not Deployment.WEB_SERVICE

    return ProjectShape(
        deployment=deployment,
        runtime_langs=runtime_langs,
        web_frameworks=web_frameworks,
        ui_lang=ui_lang,
        is_single_user=is_single_user,
    )
