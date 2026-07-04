"""Violation resolution and aggregation for the filesystem action provider."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser import parse_eval_from_json, parse_eval_markdown
from quodeq.core.types import ViolationFileEntry, ViolationResponse, ViolationSummary
from quodeq.shared.utils import _env_int, read_text
from quodeq.services.violation_context import ViolationContext  # noqa: F401 — re-export
from quodeq.services.deleted import deleted_keys as _deleted_keys
from quodeq.services.dismissed import dismissed_keys as _dismissed_keys
from quodeq.services.violations_parsing import (
    parse_violations_from_evidence,
    parse_violations_from_jsonl,
    parse_violations_from_stream,
)

_DEFAULT_MAX_VIOLATION_FILES = 20


def _max_violation_files(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the max number of violation files to include. *override* bypasses env for testing."""
    if override is not None:
        return override
    return _env_int("QUODEQ_MAX_VIOLATION_FILES", _DEFAULT_MAX_VIOLATION_FILES, env=env)


@dataclass(frozen=True)
class _ResolveOptions:
    """Injectable options for resolve_dimension_eval: filesystem callbacks and paths."""
    exists_fn: Callable[[Path], bool] = Path.exists
    stat_fn: Callable[[Path], Any] = Path.stat
    compiled_dir: Path | None = None


def _dismissed_key_for_violation(v: dict) -> tuple:
    """Build a (req, file, line) key from a violation dict.

    Handles two formats:
    - Separated: file="path/to/file.py", line=42
    - Combined: file="path/to/file.py:42", line=None
    """
    req = v.get("req", "")
    raw_file = v.get("file", "")
    line = v.get("line")
    if line is not None:
        return (req, raw_file, line)
    # Parse line from "file:line" format
    if ":" in raw_file:
        parts = raw_file.rsplit(":", 1)
        try:
            return (req, parts[0], int(parts[1]))
        except (ValueError, IndexError):
            pass
    return (req, raw_file, 0)


def _deleted_key_for_violation(v: dict, dimension: str, principle: str | None = None) -> tuple:
    """Build a (dimension, principle, file) suppression key from a violation dict.

    Parsed eval violations are camelCase (``practiceId``); ``principle`` is
    kept as a fallback for pre-camelCase dicts. Principle-group entries carry
    no principle field at all, so callers pass the group name as *principle*.
    """
    raw_file = v.get("file", "")
    if v.get("line") is None and ":" in raw_file:
        raw_file = raw_file.rsplit(":", 1)[0]
    if principle is None:
        principle = v.get("practiceId") or v.get("principle") or ""
    return (dimension or "", principle or "", raw_file)


def _filter_dismissed_from_result(
    result: "ViolationResponse | dict[str, Any] | None",
    dkeys: "set[tuple]",
    delkeys: "set[tuple] | None" = None,
    dimension: str = "",
) -> "ViolationResponse | dict[str, Any] | None":
    """Remove dismissed and permanently-deleted violations from any result format."""
    if not result or (not dkeys and not delkeys):
        return result
    if isinstance(result, dict):
        if "violations" in result:
            result["violations"] = [
                v for v in result["violations"]
                if _dismissed_key_for_violation(v) not in dkeys
                and (not delkeys or _deleted_key_for_violation(v, dimension) not in delkeys)
            ]
        for p in result.get("principles", []):
            if "violations" in p:
                group_principle = p.get("name", "") or ""
                p["violations"] = [
                    v for v in p["violations"]
                    if _dismissed_key_for_violation(v) not in dkeys
                    and (not delkeys or _deleted_key_for_violation(v, dimension, group_principle) not in delkeys)
                ]
    return result


def _try_evidence_formats(
    base: Path, dimension: str, ctx: ViolationContext,
    _exists, _stat, compiled_dir, dkeys: set[tuple], delkeys: set[tuple],
) -> ViolationResponse | dict[str, Any] | None:
    """Try evidence file formats (JSON, JSONL, stream) as fallbacks."""
    evidence_path = base / "evidence" / f"{dimension}_evidence.json"
    if _exists(evidence_path):
        return _filter_dismissed_from_result(
            parse_violations_from_evidence(evidence_path, ctx), dkeys,
            delkeys, dimension,
        )

    jsonl_path = base / "evidence" / f"{dimension}_evidence.jsonl"
    stream_path = base / "evidence" / f"{dimension}_live.stream"
    if _exists(jsonl_path) and _stat(jsonl_path).st_size > 0:
        return parse_violations_from_jsonl(
            jsonl_path, stream_path, ctx, compiled_dir=compiled_dir,
            dismissed_keys=dkeys, deleted_keys=delkeys,
        )

    if _exists(stream_path):
        return parse_violations_from_stream(stream_path, ctx)

    return None


def resolve_dimension_eval(
    base: Path, project: str, run_id: str, dimension: str,
    options: _ResolveOptions | None = None,
) -> ViolationResponse | dict[str, Any] | None:
    """Try successive file formats to load evaluation data for a dimension.

    *options* bundles injectable filesystem callbacks and the compiled
    standards directory for testing without a real FS.
    """
    opts = options or _ResolveOptions()
    _exists = opts.exists_fn
    _stat = opts.stat_fn
    compiled_dir = opts.compiled_dir
    dkeys = _dismissed_keys(base.parent)
    delkeys = _deleted_keys(base.parent)

    eval_path = base / "evaluation" / f"{dimension}.json"
    if _exists(eval_path):
        return _filter_dismissed_from_result(
            parse_eval_from_json(eval_path, project, run_id, dimension, compiled_dir=compiled_dir),
            dkeys, delkeys, dimension,
        )

    markdown_path = base / "evaluation" / f"{dimension}_eval.md"
    if _exists(markdown_path):
        try:
            content = read_text(markdown_path)
        except OSError:
            return None
        return _filter_dismissed_from_result(
            parse_eval_markdown(content, project, run_id, dimension),
            dkeys, delkeys, dimension,
        )

    ctx = ViolationContext(project=project, run_id=run_id, dimension=dimension)
    return _try_evidence_formats(base, dimension, ctx, _exists, _stat, compiled_dir, dkeys, delkeys)


def aggregate_violations(dashboard: dict[str, Any]) -> ViolationSummary:
    """Aggregate violation counts and top files from dashboard dimensions."""
    total = 0
    critical = 0
    major = 0
    minor = 0
    by_file: dict[str, dict[str, Any]] = {}
    for dim in dashboard.get("dimensions", []) or []:
        total += dim.get("totals", {}).get("violationCount", 0)
        severity = dim.get("totals", {}).get("severity", {})
        critical += severity.get("critical", 0)
        major += severity.get("major", 0)
        minor += severity.get("minor", 0)
        for violation in dim.get("violations", []) or []:
            file_path = violation.get("file")
            if not file_path:
                continue
            entry = by_file.setdefault(
                file_path, {"path": file_path, "count": 0, "critical": 0, "major": 0, "minor": 0}
            )
            entry["count"] += 1
            sev = violation.get("severity", "minor")
            if sev in entry:
                entry[sev] += 1
    # _max_violation_files() reads from env at call time; the env injection
    # parameter exists for unit-testing _max_violation_files directly.
    top_files = sorted(
        by_file.values(), key=lambda item: item["count"], reverse=True,
    )[:_max_violation_files()]
    return ViolationSummary(
        total=total,
        critical=critical,
        major=major,
        minor=minor,
        files=[ViolationFileEntry(**f) for f in top_files],
    )
