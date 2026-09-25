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
A manifest that cannot be read or whose shape is nonsense degrades that one
signal and leaves the rest intact: a per-manifest read failure (``OSError``,
a decode error) is absorbed in ``_project_shape_io.py``, deeply nested JSON
or TOML overflows the parser's call stack and is absorbed there too
(``RecursionError``), and a scalar where a list belongs raises ``TypeError``
with every parser succeeding, caught by ``detect_shape``'s own boundary.
``detect_shape``'s four callers (``_api_runner``, ``api_prompt_assembly``,
``mcp/findings_server``, and the ``context`` re-export) do not add their own
guard, so those are the failure modes this module absorbs; anything else
propagates to the caller's own fault-isolation boundary.

``Deployment`` / ``ProjectShape`` live in ``_project_shape_types.py``;
manifest-reading helpers live in ``_project_shape_io.py``; per-ecosystem
signal detectors live in ``_project_shape_signals.py`` -- all split out to
keep this module under the size ratchet's 300-line cap and re-exported (or,
for the private signal functions, imported and called) from here.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.context._project_shape_types import Deployment, ProjectShape  # re-export
from quodeq.context._project_shape_signals import (
    detect_runtime_langs, go_signals, node_signals, python_signals, rust_signals,
)

_logger = logging.getLogger(__name__)


def detect_shape(repo_path: Path) -> ProjectShape:
    """Detect a :class:`ProjectShape` from manifests at *repo_path*.

    Falls back to ``Deployment.UNKNOWN`` whenever signals are absent or
    contradictory; callers must treat ``UNKNOWN`` as a no-op (no downweight,
    no prompt enrichment).
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        return ProjectShape()

    try:
        py_dep, py_web, _ = python_signals(repo)
        js_dep, js_web, _, ui_lang = node_signals(repo)
        rust_dep = rust_signals(repo)
        go_dep = go_signals(repo)
    except (OSError, TypeError) as exc:
        _logger.warning(
            "Manifest signal detection failed for %s, degrading to UNKNOWN: %s", repo, exc,
        )
        return ProjectShape()

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
    runtime_langs = detect_runtime_langs(repo)
    is_single_user = deployment is not Deployment.WEB_SERVICE

    return ProjectShape(
        deployment=deployment,
        runtime_langs=runtime_langs,
        web_frameworks=web_frameworks,
        ui_lang=ui_lang,
        is_single_user=is_single_user,
    )
