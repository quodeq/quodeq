"""Validation pipeline for evaluator file imports."""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from quodeq.shared.errors import ClientMessageError

_ALLOWED_TOP = {"id", "name", "description", "weight", "source", "principles"}
_ALLOWED_PRINCIPLE = {"name", "description", "requirements"}
_ALLOWED_REQUIREMENT = {"id", "text", "description", "refs"}
_ALLOWED_REF = {"source", "id", "name", "url"}

_MAX_NAME = 500
_MAX_DESCRIPTION = 2000
_MAX_REQ_TEXT = 2000

_FIELD_NAME = "name"
_FIELD_DESCRIPTION = "description"
_NAME_AND_DESCRIPTION_LIMITS = ((_FIELD_NAME, _MAX_NAME), (_FIELD_DESCRIPTION, _MAX_DESCRIPTION))  # standard + principle
_REQUIREMENT_LIMITS = (("text", _MAX_REQ_TEXT), (_FIELD_DESCRIPTION, _MAX_DESCRIPTION))  # requirement text fields

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+|previous\s+)?(instructions|prompts)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"new\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"disregard", re.IGNORECASE),
    re.compile(r"override\s+(all|previous|your)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+|previous\s+)", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
    re.compile(r"\n{10,}"),
]


class StandardImportValidationError(ClientMessageError, ValueError):
    """Raised when an imported payload fails :func:`validate_import`.

    Carries the validator's own field-level reasons so a caller can report
    them without re-running validation: ``errors`` is that list and
    ``public_message`` (from ClientMessageError) the joined text an API route
    may return to the client verbatim, never ``str(exc)`` -- see
    tests/api/test_no_exception_echo.py. Stays a ``ValueError`` so callers
    that only distinguish "invalid payload" keep working.
    """

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _truncate(value: str, limit: int) -> str:
    return value[:limit] if len(value) > limit else value


def _truncate_field(cleaned: dict, key: str, limit: int) -> None:
    """Truncate ``cleaned[key]`` in place to *limit* chars, when it is a present string."""
    if key in cleaned and isinstance(cleaned[key], str):
        cleaned[key] = _truncate(cleaned[key], limit)


def _pick(source: dict, allowed: set[str], limits: tuple[tuple[str, int], ...] = ()) -> dict:
    """*source* reduced to the *allowed* keys, each ``(key, limit)`` in *limits* truncated."""
    cleaned = {k: source[k] for k in allowed if k in source}
    for key, limit in limits:
        _truncate_field(cleaned, key, limit)
    return cleaned


def _whitelist_children(cleaned: dict, key: str, whitelist: Callable[[dict], dict]) -> None:
    """Replace a list under *key* in place by its dict items, each run through *whitelist*."""
    if isinstance(cleaned.get(key), list):
        cleaned[key] = [whitelist(item) for item in cleaned[key] if isinstance(item, dict)]


def _whitelist_ref(ref: dict) -> dict:
    return _pick(ref, _ALLOWED_REF)


def _whitelist_requirement(req: dict) -> dict:
    cleaned = _pick(req, _ALLOWED_REQUIREMENT, _REQUIREMENT_LIMITS)
    _whitelist_children(cleaned, "refs", _whitelist_ref)
    return cleaned


def _whitelist_principle(principle: dict) -> dict:
    cleaned = _pick(principle, _ALLOWED_PRINCIPLE, _NAME_AND_DESCRIPTION_LIMITS)
    _whitelist_children(cleaned, "requirements", _whitelist_requirement)
    return cleaned


def _identity_errors(data: dict) -> list[str]:
    """Complaints about the evaluator's own id and name.

    The id becomes a path segment, so it may not carry separators or
    parent-traversal.
    """
    errors: list[str] = []
    if not isinstance(data.get("id"), str) or not data["id"]:
        errors.append("Missing required field: id")
    else:
        sid = data["id"]
        if "/" in sid or "\\" in sid or ".." in sid:
            errors.append(f"Invalid id: {sid!r} (must not contain /, \\, or ..)")
    if not isinstance(data.get("name"), str) or not data["name"]:
        errors.append("Missing required field: name")
    return errors


def _one_principle_errors(index: int, principle: object) -> list[str]:
    """Complaints about the principle at *index*, named by position for the user."""
    if not isinstance(principle, dict):
        return [f"Principle {index} must be an object"]
    errors: list[str] = []
    if not isinstance(principle.get("name"), str) or not principle["name"]:
        errors.append(f"Principle {index} missing required field: name")
    if "requirements" not in principle:
        errors.append(f"Principle {index} missing required field: requirements")
    elif not isinstance(principle["requirements"], list):
        errors.append(f"Principle {index} field 'requirements' must be a list")
    return errors


def _principle_errors(data: dict) -> list[str]:
    """Complaints about the principles list and each principle in it."""
    if "principles" not in data:
        return ["Missing required field: principles"]
    if not isinstance(data["principles"], list):
        return ["Field 'principles' must be a list"]
    errors: list[str] = []
    for i, p in enumerate(data["principles"]):
        errors.extend(_one_principle_errors(i, p))
    return errors


def _sanitized(data: dict) -> dict:
    """*data* reduced to the allowed keys, with every text field truncated."""
    cleaned = _pick(data, _ALLOWED_TOP, _NAME_AND_DESCRIPTION_LIMITS)
    _whitelist_children(cleaned, "principles", _whitelist_principle)
    return cleaned


def validate_import(data: dict) -> dict:
    """Validate and sanitize an imported evaluator.

    Returns ``{"valid": True, "errors": [], "data": sanitized_dict}``
    on success, or ``{"valid": False, "errors": [...], "data": None}``
    on failure.
    """
    errors = _identity_errors(data) + _principle_errors(data)
    if errors:
        return {"valid": False, "errors": errors, "data": None}
    return {"valid": True, "errors": [], "data": _sanitized(data)}


def _match_patterns(text: str, patterns: Sequence[re.Pattern]) -> list[re.Match]:
    """Every pattern in *patterns* that hits *text*, in pattern order."""
    return [m for m in (p.search(text) for p in patterns) if m is not None]


def scan_text(text: str) -> list[str]:
    """Return injection warnings for arbitrary untrusted text (empty == clean)."""
    return [
        f"suspicious content matches {m.re.pattern!r}"
        for m in _match_patterns(text, _INJECTION_PATTERNS)
    ]


def scan_injection(data: dict) -> list[str]:
    """Scan all string fields for potential LLM injection patterns.

    Returns a list of human-readable warning strings.  Empty list means clean.
    """
    warnings: list[str] = []

    def _check(text: str, location: str) -> None:
        for m in _match_patterns(text, _INJECTION_PATTERNS):
            warnings.append(f"Suspicious text in {location}: contains '{m.group()}'")

    for field in (_FIELD_NAME, _FIELD_DESCRIPTION, "source"):
        if isinstance(data.get(field), str):
            _check(data[field], f"standard {field}")

    for i, p in enumerate(data.get("principles", [])):
        if not isinstance(p, dict):
            continue
        for field in (_FIELD_NAME, _FIELD_DESCRIPTION):
            if isinstance(p.get(field), str):
                _check(p[field], f"principle '{p.get('name', i)}' {field}")
        for j, r in enumerate(p.get("requirements", [])):
            if not isinstance(r, dict):
                continue
            for field in ("text", _FIELD_DESCRIPTION):
                if isinstance(r.get(field), str):
                    _check(r[field], f"principle '{p.get('name', i)}', requirement {j}")

    return warnings
