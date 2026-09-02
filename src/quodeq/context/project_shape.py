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

``Deployment`` / ``ProjectShape`` live in ``_project_shape_types.py``;
manifest-reading helpers live in ``_project_shape_io.py``; per-ecosystem
signal detectors live in ``_project_shape_signals.py`` -- all split out to
keep this module under the size ratchet's 300-line cap and re-exported (or,
for the private signal functions, imported and called) from here.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.context._project_shape_types import Deployment, ProjectShape  # noqa: F401 - re-export
from quodeq.context._project_shape_signals import (
    _detect_runtime_langs, _go_signals, _node_signals, _python_signals, _rust_signals,
)


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
