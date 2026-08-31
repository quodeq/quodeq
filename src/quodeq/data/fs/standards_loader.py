"""Standards loading from disk — the I/O half of the standards layer.

``core/standards`` keeps the pure extraction functions (``extract_refs``,
``extract_requirements``, ``ref_label``); everything that touches the
filesystem lives here, so the core layer stays free of I/O. Callers that
already hold the parsed data should use the pure functions directly.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.standards.refs import (
    extract_refs,
    extract_requirement_checks,
    extract_requirements,
)
from quodeq.core.utils.io import read_json
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def known_dimension_ids(
    compiled_dir: str | Path | None, evaluators_dir: str | Path | None = None,
) -> frozenset[str]:
    """Return the dimension ids actually installed on disk.

    A dimension is "known" when a same-named ``<id>.json`` file sits
    directly inside *compiled_dir* (built-in, compiled standards) or
    *evaluators_dir* (custom, user-imported standards) -- the two places a
    standard's definition can live. The set is rebuilt from a directory
    listing every call rather than cached, so a newly imported custom
    standard is recognised immediately.

    Listing is the point, not joining: a traversal segment or absolute path
    never matches a real directory entry, so there is nothing to sanitise --
    the caller compares the candidate dimension against this set before
    building any path from it.
    """
    ids: set[str] = set()
    for directory in (compiled_dir, evaluators_dir):
        if not directory:
            continue
        path = Path(directory)
        if not path.is_dir():
            continue
        ids.update(p.stem for p in path.glob("*.json"))
    return frozenset(ids)


def is_known_dimension(
    dimension: str | None,
    compiled_dir: str | Path | None,
    evaluators_dir: str | Path | None = None,
) -> bool:
    """True if *dimension* names a standard actually installed on disk.

    Comparison is case-insensitive, matching every other place dimension ids
    are compared in this codebase (see
    ``core.standards.visibility.normalize_ids``): older eval payloads and
    request values may carry ``"Security"`` where a fresh compile writes
    ``security.json``, and both must be recognised as the same dimension.
    """
    if not dimension:
        return False
    known_lower = {d.lower() for d in known_dimension_ids(compiled_dir, evaluators_dir)}
    return dimension.lower() in known_lower


def _load_compiled_data(
    compiled_dir: str | Path | None, dimension: str | None,
    evaluators_dir: Path | None = None,
) -> dict | None:
    """Load raw compiled standards JSON from *compiled_dir*. Returns None on error.

    Falls back to *evaluators_dir* for custom evaluators when provided.

    *dimension* is request-reachable (routed here from the action API's
    per-dimension endpoints), so it is checked against
    :func:`is_known_dimension` before it ever reaches a path join. A
    dimension outside that installed set is treated the same as one with no
    compiled data at all: this returns ``None`` rather than raising, matching
    every other failure mode in this function.
    """
    if not dimension:
        return None
    if (compiled_dir or evaluators_dir) and not is_known_dimension(
        dimension, compiled_dir, evaluators_dir,
    ):
        _logger.warning("Rejected unknown dimension for compiled standards lookup: %r", dimension)
        return None
    if compiled_dir:
        path = Path(compiled_dir) / f"{dimension}.json"
        if path.is_file():
            try:
                return read_json(path)
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                _logger.warning("Failed to load compiled standards for %s: %s", dimension, exc)
                return None
    if evaluators_dir:
        evaluators_path = evaluators_dir / f"{dimension}.json"
        if evaluators_path.is_file():
            try:
                return read_json(evaluators_path)
            except (OSError, ValueError, UnicodeDecodeError):
                return None
    return None


def load_compiled_refs(
    compiled_dir: str | Path | None, dimension: str | None,
    evaluators_dir: Path | None = None,
) -> dict[str, list[dict]]:
    """Load ``{req_id: [{label, url, ...}, ...]}`` from compiled standards on disk."""
    data = _load_compiled_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if not data:
        return {}
    return extract_refs(data)


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


def load_requirement_checks(
    compiled_dir: str | Path | None, dimension: str | None,
    evaluators_dir: Path | None = None,
) -> dict[str, frozenset[str]]:
    """Load ``{check_name: {req_id, ...}}`` for *dimension* from disk.

    Empty when the dimension has no standard on disk or none of its
    requirements declares a checker -- both mean "nothing deterministic to
    run", which callers treat identically.
    """
    data = _load_compiled_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if not data:
        return {}
    return extract_requirement_checks(data)


def read_req_to_principle_map(directory: Path, dimension: str) -> dict[str, str] | None:
    """Read ``<directory>/<dimension>.json`` into a req-id → principle-name map.

    The file-reading half of ``core.evidence._req_mapping``: core injects this
    as its ``req_map_reader`` so evidence grouping never touches the
    filesystem itself. The contract is an empty map on any missing, unreadable
    or malformed input so callers stay permissive, never a crash.
    """
    if directory is None or not directory.is_dir():
        return {}
    path = directory / f"{dimension}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping: dict[str, str] = {}
        for principle in data.get("principles", []):
            pname = principle.get("name", "")
            for req in principle.get("requirements", []):
                rid = req.get("id", "")
                if rid and pname:
                    mapping[rid] = pname
        return mapping
    except (OSError, ValueError, AttributeError, TypeError):
        # AttributeError/TypeError: a valid-JSON-but-non-dict payload (a list
        # or null at the top level, or non-dict principle/requirement items)
        # makes .get() raise.
        return {}


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
