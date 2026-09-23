"""Helpers the read tools share: dimension-id validation, the findings
repository fallback, raw eval-report loading and requirement-id extraction.

A leaf: it imports none of ``_read_tools``, ``_read_tools_scope`` or
``_read_tools_violations``, so those three import it without a cycle.
"""
from __future__ import annotations

import re
from pathlib import Path

from quodeq.assistant.tools.registry import ToolError
from quodeq.data.fs.report_parser.finding_details import iter_eval_reports
from quodeq.data.ports.findings import FindingsRepository

# Dimension ids are simple slugs. The tool-call `dimension` argument is
# model-controlled text used to build a file path, so anything outside this
# charset (path separators, dots, absolute paths) is rejected outright.
DIMENSION_RE = re.compile(r"[a-z0-9_-]+")


def validate_dimension(dimension: str) -> str:
    """Return *dimension* if it is a plain slug, else raise ToolError."""
    if not isinstance(dimension, str) or not DIMENSION_RE.fullmatch(dimension):
        raise ToolError(f"invalid dimension: {dimension!r}")
    return dimension


def default_findings_repo_factory(run_dir: Path) -> FindingsRepository:
    """Composition fallback: the concrete SQLite findings repository.

    Real composition roots (``api._assistant_helpers.build_tool_context``,
    the MCP server) pass ``ToolContext.findings_repo_factory`` explicitly;
    this lazy default keeps directly-constructed contexts working without
    coupling the context module (or this module's import time) to SQLite.
    """
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    return SqliteFindingsRepository(run_dir)


def raw_run_dims(eval_dir: Path) -> list[dict]:
    """A run's evaluation reports as dicts, each guaranteed a ``dimension``.

    Mirrors the pre-filtering fallback ``data.get("dimension", path.stem)``: a
    report that omits the field is named after its file rather than dropped.
    """
    out: list[dict] = []
    for dimension, data in iter_eval_reports(eval_dir):
        data.setdefault("dimension", dimension)
        out.append(data)
    return out


def requirement_of(v: dict) -> str:
    """The requirement id of a violation, normalized to ``""`` when absent.

    It is the FIRST element of the (req, file, line) identity that
    dismiss/verify and the suppression filter key on. Run-scoped eval JSON
    and the accumulated serialized-Finding payload both key it as "req";
    "requirement" is accepted for any producer that already renamed it.
    """
    return str(v.get("req") or v.get("requirement") or "")
