"""Prompt assembly for the direct API runner.

Loads api_prompt.md template and fills in source files, standards,
and evaluation rules.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.analysis.prompts._template import load_template
from quodeq.analysis.prompts.builder import _load_evaluation_rules
from quodeq.config.prompt_templates import render_template
from quodeq.context.path_role import Role, path_role
from quodeq.context.project_shape import Deployment, ProjectShape, detect_shape
from quodeq.context.trust_model import TrustModel

_log = logging.getLogger(__name__)

_FINDING_SCHEMA = """\
Each finding must be a JSON object with these fields:
  Required:
    "req": string - requirement ID (e.g. "M-MOD-1", "S-CON-3")
    "t": string - "violation" or "compliance"
    "file": string - file path relative to repo root
    "line": integer - line number
    "severity": string - "critical", "major", or "minor"
    "w": string - short title of the finding
    "reason": string - 1–3 sentences: what the quoted code does wrong AS WRITTEN, plus the concrete impact
    "snippet": string - offending code copied VERBATIM from the source (one or a few contiguous lines, exact characters)
  Optional:
    "end_line": integer - last line if multi-line
    "scope": string - "file", "class", or "module"
    "vt": string - violation type taxonomy code: a short, stable, kebab-case class of the violation (e.g. "code-injection", "hardcoded-secret", "missing-error-handling"); reuse the exact same code for every finding of the same kind
"""


def _read_file_safe(path: Path) -> str | None:
    """Read a file, returning None on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _log.warning("Could not read file: %s", path)
        return None


def _role_label(display_path: str) -> str:
    """Return a `(role: <role>)` suffix for non-prod paths, empty otherwise.

    Tells the LLM the surrounding code's purpose so it can tone down findings
    that don't matter outside production code (e.g. brittle test fixtures).
    """
    role = path_role(display_path)
    if role is Role.PROD:
        return ""
    return f" (role: {role.value})"


def _build_files_block(source_files: list[Path], repo_root: Path | None = None) -> str:
    """Build the source files block for the prompt."""
    parts: list[str] = []
    for path in source_files:
        content = _read_file_safe(path)
        if content is None:
            continue
        # Always emit POSIX-style separators so the LLM sees the same path
        # shape on every host. str(path.relative_to(...)) yields backslashes
        # on Windows, which are unusual in code prompts and inconsistent
        # with the path-role classifier's normalisation.
        display_path = path.relative_to(repo_root).as_posix() if repo_root else path.name
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(content.splitlines()))
        parts.append(f"### {display_path}{_role_label(display_path)}\n```\n{numbered}\n```")
    return "\n\n".join(parts)


def _build_shape_summary_parts(
    shape: ProjectShape, trust_model: TrustModel | None,
) -> list[str]:
    """Build the `key=value` summary fragments for a project-shape briefing."""
    parts: list[str] = []
    if shape.deployment is not Deployment.UNKNOWN:
        parts.append(f"deployment={shape.deployment.value}")
        parts.append(f"single_user={'true' if shape.is_single_user else 'false'}")
    if trust_model is not None:
        parts.append(f"multi_tenant={'true' if trust_model.multi_tenant else 'false'}")
        parts.append(f"network_exposure={trust_model.network_exposure}")
    if shape.runtime_langs:
        parts.append(f"runtime={'+'.join(shape.runtime_langs)}")
    if shape.web_frameworks:
        parts.append(f"web_frameworks={'+'.join(shape.web_frameworks)}")
    if shape.ui_lang:
        parts.append(f"ui={shape.ui_lang}")
    return parts


def _deployment_note(shape: ProjectShape) -> str:
    """Return a deployment-specific caveat for the LLM, or "" when none applies."""
    if shape.deployment is Deployment.DESKTOP and shape.is_single_user:
        return (
            " This is a single-user desktop tool, not a hosted multi-tenant"
            " service. Treat findings about thread blocking, distributed"
            " state, concurrent callers, and rate limiting with skepticism."
        )
    if shape.deployment is Deployment.LIBRARY:
        return (
            " This is a library, not an end-user application. API stability"
            " and backwards compatibility matter more than user-facing UX."
        )
    if shape.deployment is Deployment.CLI and shape.is_single_user:
        return (
            " This is a single-user CLI, not a hosted service. Concurrent"
            " caller and multi-tenant findings rarely apply."
        )
    return ""


def _trust_relaxation_notes(trust_model: TrustModel | None) -> str:
    """Return trust-relaxation caveats for the LLM, or "" when none apply.

    Both notes below mirror scope_gate.py's own two rules, deliberately at
    the same preconditions, so the prompt never advises something the
    deterministic gate would not also do. Neither ever tells the model a
    category "does not apply" -- that invites the model to omit the
    finding, which is unrecoverable, unlike a severity cap. Always report;
    only the severity guidance changes.
    """
    note = ""
    if trust_model is not None and trust_model.relaxes_remote():
        note += (
            " No untrusted party can open a socket to this process. For a"
            " path or key finding whose source you cannot name, still report"
            " it, at `minor` instead of `major`. Do not omit it."
        )
    # The second axis check requires relaxes_remote() too, same as the
    # gate's cross_principal rule: multi_tenant=False alone says nothing
    # about whether a stranger can reach the process, so on a public,
    # single-tenant project an authorization finding stays fully in scope.
    if (trust_model is not None and not trust_model.multi_tenant
            and trust_model.relaxes_remote()):
        note += (
            " There is exactly one user account. For an authorization"
            " finding whose only issue is reaching another user's data, still"
            " report it, at `minor` instead of `major`. Do not omit it."
        )
    return note


def _format_shape_block(
    shape: ProjectShape, trust_model: TrustModel | None = None,
) -> str:
    """Render a project briefing for the LLM, or empty when nothing is known.

    A declared trust model is briefed even when shape detection returned
    UNKNOWN: detection is a guess, the declaration is the team telling us the
    answer, and suppressing it would waste the only reliable signal we have.
    """
    relaxing = trust_model is not None and (
        trust_model.relaxes_remote() or not trust_model.multi_tenant)
    if shape.deployment is Deployment.UNKNOWN and not relaxing:
        return ""
    summary = ", ".join(_build_shape_summary_parts(shape, trust_model))
    note = _deployment_note(shape) + _trust_relaxation_notes(trust_model)
    return f"## Project Shape\n\n**{summary}**.{note}"


def assemble_api_prompt(
    *,
    source_files: list[Path],
    standards_text: str,
    dimension: str,
    repo_name: str,
    repo_root: Path | None = None,
    project_shape: ProjectShape | None = None,
    trust_model: TrustModel | None = None,
) -> str:
    """Assemble a complete evaluation prompt for the API runner.

    *project_shape* is computed from *repo_root* when not supplied; pass an
    explicit shape to skip detection (e.g. when a cached shape is being
    reused across dimensions). *trust_model* is never detected here -- it is
    resolved by the caller (declared profile, then detection, then the
    conservative default) and threaded through so the model is briefed on
    the same trust boundary the deterministic scope gate enforces.
    """
    template = load_template(template_name="api_prompt.md")
    rules = _load_evaluation_rules()
    files_block = _build_files_block(source_files, repo_root=repo_root)
    if project_shape is None and repo_root is not None:
        project_shape = detect_shape(repo_root)
    # Fall back to an UNKNOWN shape rather than skipping the block outright:
    # a declared trust model must still be briefed even without a shape
    # verdict. _format_shape_block itself returns "" when nothing is known.
    shape_block = _format_shape_block(project_shape or ProjectShape(), trust_model)
    return render_template(template, {
        "DIMENSION": dimension,
        "REPO_NAME": repo_name,
        "STANDARDS_TEXT": standards_text,
        "PROJECT_SHAPE": shape_block,
        "EVALUATION_RULES": rules,
        "FINDING_SCHEMA": _FINDING_SCHEMA,
        "FILES_BLOCK": files_block,
    })
