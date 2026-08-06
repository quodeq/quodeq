"""Detect a project's deployment shape from its manifest files.

Reads ``pyproject.toml``, ``package.json``, ``Cargo.toml``, ``go.mod`` and
similar at the repo root and produces a :class:`ProjectShape`. Detection is
language-agnostic: every check is a manifest pattern, never a code-level
assumption.

The shape is the single biggest source of false positives in the current
audit corpus (~40%) because the scanner defaults to "hosted multi-tenant
web service" assumptions on what is in fact a desktop / CLI / library.

Every manifest here is *analyzed*, untrusted input from the repository under
evaluation, and detection is advisory with a well-defined UNKNOWN fallback.
So nothing in this module may raise: a manifest that cannot be read or whose
shape is nonsense degrades that one signal and leaves the rest intact. That
has to hold against every failure mode, not the well-behaved ones -- deeply
nested JSON or TOML overflows the parser's call stack and raises
``RecursionError``, a ``RuntimeError`` subclass, and a scalar where a list
belongs raises ``TypeError`` with every parser succeeding. ``detect_shape``
has four callers that guard nothing (``_api_runner``, ``api_prompt_assembly``,
``mcp/findings_server``, and the ``context`` re-export), so an escape here
fails the whole run.
"""
from __future__ import annotations

import json
import logging
import re
import tomllib
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

_logger = logging.getLogger(__name__)


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


#: Detection probes every manifest it knows about, so most repos miss most of
#: them: a Python project has no Cargo.toml, and Quodeq's own root has neither
#: Cargo.toml nor package.json. Absence is the expected case and belongs at
#: debug. A manifest that exists and still cannot be read -- no permission, a
#: truncated file, a parser blowing its stack -- is a signal we meant to have
#: and lost, so that stays at WARNING.
#:
#: The exception type cannot carry that split on its own: opening a directory
#: raises IsADirectoryError on POSIX but PermissionError (WinError 5) on
#: Windows, which is indistinguishable from a genuine permission denial. So
#: the not-a-file cases are settled up front by ``_manifest_missing`` (the
#: same ``is_file()`` gate ``trust_model._read_profile`` uses) and the catch
#: below only has to cover a file that disappears between the check and the
#: open -- a race nobody can act on, so it stays quiet too.
_ABSENT_MANIFEST = (FileNotFoundError, IsADirectoryError, NotADirectoryError)


def _manifest_missing(path: Path) -> bool:
    """True when *path* is not a readable regular file, on any platform.

    ``Path.is_file()`` swallows its own OSError and answers False for a
    missing entry, a directory and a broken symlink alike, which is exactly
    the set that means "this project does not ship this manifest".
    """
    if path.is_file():
        return False
    _logger.debug("No manifest at %s", path)
    return True


def _read_text(path: Path) -> str | None:
    if _manifest_missing(path):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except _ABSENT_MANIFEST:
        _logger.debug("Manifest %s vanished mid-scan", path)
        return None
    except Exception as exc:  # noqa: BLE001 - detection must never fail a scan
        _logger.warning("Ignoring unreadable manifest %s: %s", path, exc)
        return None


def _read_toml(path: Path) -> dict[str, object] | None:
    if _manifest_missing(path):
        return None
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except _ABSENT_MANIFEST:
        _logger.debug("Manifest %s vanished mid-scan", path)
        return None
    except Exception as exc:  # noqa: BLE001 - detection must never fail a scan
        # Wider than OSError/TOMLDecodeError on purpose: tomllib is a
        # recursive-descent parser, so deeply nested tables overflow the stack
        # and raise RecursionError. It bottoms out far shallower than the C
        # JSON decoder -- a few thousand levels, not tens of thousands.
        _logger.warning("Ignoring unreadable TOML manifest %s: %s", path, exc)
        return None


def _read_json(path: Path) -> dict[str, object] | None:
    # Absence is already handled quietly by _read_text, so reaching the handler
    # below means the file exists and its contents are unusable.
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - detection must never fail a scan
        # Wider than json.JSONDecodeError: deeply nested arrays exhaust the C
        # decoder's call stack and raise RecursionError, a RuntimeError.
        _logger.warning("Ignoring unreadable JSON manifest %s: %s", path, exc)
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
