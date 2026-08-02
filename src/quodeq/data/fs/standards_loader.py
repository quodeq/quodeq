"""Standards loading from disk — the I/O half of the standards layer.

``core/standards`` keeps the pure extraction functions (``extract_refs``,
``extract_requirements``, ``ref_label``); everything that touches the
filesystem lives here, so the core layer stays free of I/O. Callers that
already hold the parsed data should use the pure functions directly.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.core.standards.refs import (
    _load_compiled_data,
    extract_requirements,
    load_compiled_refs,
)
from quodeq.core.utils.io import read_json
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def load_compiled_refs_multi(
    compiled_dir: str | Path | None, dimensions: list[str],
    evaluators_dir: Path | None = None,
) -> dict[str, list[dict]]:
    """Load refs for multiple dimensions, merging into a single lookup."""
    merged: dict[str, list[dict]] = {}
    for dim in dimensions:
        merged.update(load_compiled_refs(compiled_dir, dim, evaluators_dir=evaluators_dir))
    return merged


def load_compiled_requirements_multi(
    compiled_dir: str | Path | None, dimensions: list[str],
    evaluators_dir: Path | None = None,
    overrides: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Load requirements for multiple dimensions, merging into a single lookup."""
    merged: dict[str, dict] = {}
    for dim in dimensions:
        merged.update(load_compiled_requirements(
            compiled_dir, dim,
            evaluators_dir=evaluators_dir,
            overrides=overrides,
        ))
    return merged


def load_compiled_requirements(
    compiled_dir: str | Path | None, dimension: str | None,
    evaluators_dir: Path | None = None,
    overrides: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Load {req_id: {principle, text}} from compiled standards on disk.

    When *overrides* is supplied, requirement text placeholders are resolved
    using the per-requirement override values.

    Backward-compat convenience wrapper that handles file I/O then delegates
    to the pure :func:`extract_requirements`.  Used by the MCP server to
    auto-fill principle name and requirement text from the requirement ID.
    """
    data = _load_compiled_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if not data:
        return {}
    return extract_requirements(data, overrides=overrides)


def build_req_refs_lookup(compiled_dir: Path, dimension: str) -> dict[str, list[dict]]:
    """Return ``{req_id: [{label, url}, ...]}`` for every requirement's refs.

    Was a passthrough in ``core/evidence/_refs``; it belongs with the other
    disk loaders so the core layer performs no file access.
    """
    return load_compiled_refs(str(compiled_dir), dimension)


def _resolve_standards_dir(standards_dir: Path | None = None, *, paths_fn=None) -> Path:
    """Return *standards_dir* or fall back to *paths_fn()*.

    *paths_fn* is an injectable factory that must be supplied by outer layers
    (e.g. ``config.paths.default_paths``).  The core layer does not resolve
    infrastructure paths itself.
    """
    if standards_dir is not None:
        return standards_dir
    if paths_fn is None:
        raise ValueError(
            "standards_dir or paths_fn must be provided; "
            "the core layer cannot resolve infrastructure paths"
        )
    return paths_fn().standards_dir


def _load_json(path: Path, label: str) -> dict:
    """Read and parse a JSON file, raising :class:`FileNotFoundError` on failure.

    *label* is used in the error message to describe what could not be loaded.
    """
    try:
        return read_json(path)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot load {label}") from exc


def load_dimension(dimension_id: str, standards_dir: Path | None = None, *, paths_fn=None) -> dict:
    """Load an ISO 25010 dimension definition by its identifier."""
    validate_path_segment(dimension_id)
    resolved = _resolve_standards_dir(standards_dir, paths_fn=paths_fn)
    path = resolved / "iso25010" / f"{dimension_id}.json"
    return _load_json(path, f"dimension '{dimension_id}'")


def load_asvs_l1(standards_dir: Path | None = None, *, paths_fn=None) -> dict:
    """Load OWASP ASVS Level 1 requirements."""
    resolved = _resolve_standards_dir(standards_dir, paths_fn=paths_fn)
    path = resolved / "asvs" / "level1.json"
    return _load_json(path, "ASVS L1 standards")


def load_cisq(characteristic: str, standards_dir: Path | None = None, *, paths_fn=None) -> dict:
    """Load a CISQ quality characteristic definition by name."""
    validate_path_segment(characteristic)
    resolved = _resolve_standards_dir(standards_dir, paths_fn=paths_fn)
    path = resolved / "cisq" / f"{characteristic}.json"
    return _load_json(path, f"CISQ '{characteristic}'")
