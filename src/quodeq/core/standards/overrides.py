"""Per-project overrides for declared numeric requirement parameters.

Requirements may declare a ``params`` block whose values fill ``{name}``
placeholders in the requirement text. A project can override the defaults
via ``<project root>/.quodeq/standards-overrides.json``:

    {"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}

Invalid entries are skipped with a warning; a bad file never fails analysis.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

OVERRIDES_RELPATH = Path(".quodeq") / "standards-overrides.json"
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def load_project_overrides(project_root: str | Path | None) -> dict[str, dict]:
    """Load ``{req_id: {param: value}}``; ``{}`` when absent or malformed."""
    if not project_root:
        return {}
    path = Path(project_root) / OVERRIDES_RELPATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Ignoring malformed standards overrides %s: %s", path, exc)
        return {}
    overrides = data.get("overrides") if isinstance(data, dict) else None
    if not isinstance(overrides, dict):
        _logger.warning("Ignoring standards overrides %s: no 'overrides' object", path)
        return {}
    return {req_id: vals for req_id, vals in overrides.items() if isinstance(vals, dict)}


def _is_valid(value: object, spec: dict) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return spec.get("min", value) <= value <= spec.get("max", value)


def effective_params(req: dict, req_overrides: dict | None) -> dict[str, int]:
    """Effective ``{param: value}``: valid override wins, else declared default."""
    values: dict[str, int] = {}
    for name, spec in (req.get("params") or {}).items():
        value = spec.get("default")
        if req_overrides and name in req_overrides:
            candidate = req_overrides[name]
            if _is_valid(candidate, spec):
                value = candidate
            else:
                _logger.warning(
                    "Ignoring invalid override %s=%r for requirement %s",
                    name, candidate, req.get("id"))
        values[name] = value
    return values


def resolve_requirement_text(req: dict, req_overrides: dict | None = None) -> str:
    """Substitute effective param values into the requirement text template."""
    text = req.get("text", "")
    if not req.get("params"):
        return text
    values = effective_params(req, req_overrides)
    return _PLACEHOLDER_RE.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0),
        text)


def collect_declared_params(compiled_dir: Path) -> dict[str, dict]:
    """Collect ``{req_id: params_spec}`` across every compiled dimension file."""
    declared: dict[str, dict] = {}
    for path in sorted(Path(compiled_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for principle in data.get("principles", []):
            for req in principle.get("requirements", []):
                if req.get("id") and req.get("params"):
                    declared[req["id"]] = req["params"]
    return declared


def validate_overrides(raw: object, declared: dict[str, dict]) -> tuple[dict, list[str]]:
    """Validate a full overrides mapping; returns ``(clean, errors)``.

    ``clean`` is empty whenever ``errors`` is non-empty — API writes are
    all-or-nothing, unlike analysis-time loading which skips bad entries.
    """
    if not isinstance(raw, dict):
        return {}, ["overrides must be an object"]
    clean: dict[str, dict] = {}
    errors: list[str] = []
    for req_id, params in raw.items():
        specs = declared.get(req_id)
        if specs is None:
            errors.append(f"{req_id}: unknown requirement or no declared params")
            continue
        if not isinstance(params, dict):
            errors.append(f"{req_id}: value must be an object")
            continue
        clean_params: dict[str, int] = {}
        for name, value in params.items():
            spec = specs.get(name)
            if spec is None:
                errors.append(f"{req_id}.{name}: unknown parameter")
            elif not _is_valid(value, spec):
                errors.append(
                    f"{req_id}.{name}: must be an integer between "
                    f"{spec['min']} and {spec['max']}")
            else:
                clean_params[name] = value
        if clean_params:
            clean[req_id] = clean_params
    return ({}, errors) if errors else (clean, errors)
