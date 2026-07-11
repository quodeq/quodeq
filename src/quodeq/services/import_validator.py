"""Validation pipeline for evaluator file imports."""
from __future__ import annotations

import re

_ALLOWED_TOP = {"id", "name", "description", "weight", "source", "principles"}
_ALLOWED_PRINCIPLE = {"name", "description", "requirements"}
_ALLOWED_REQUIREMENT = {"id", "text", "description", "refs"}
_ALLOWED_REF = {"source", "id", "name", "url"}

_MAX_NAME = 500
_MAX_DESCRIPTION = 2000
_MAX_REQ_TEXT = 2000

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


def _truncate(value: str, limit: int) -> str:
    return value[:limit] if len(value) > limit else value


def _whitelist_ref(ref: dict) -> dict:
    return {k: ref[k] for k in _ALLOWED_REF if k in ref}


def _whitelist_requirement(req: dict) -> dict:
    cleaned = {k: req[k] for k in _ALLOWED_REQUIREMENT if k in req}
    if "text" in cleaned and isinstance(cleaned["text"], str):
        cleaned["text"] = _truncate(cleaned["text"], _MAX_REQ_TEXT)
    if "description" in cleaned and isinstance(cleaned["description"], str):
        cleaned["description"] = _truncate(cleaned["description"], _MAX_DESCRIPTION)
    if "refs" in cleaned and isinstance(cleaned["refs"], list):
        cleaned["refs"] = [_whitelist_ref(r) for r in cleaned["refs"] if isinstance(r, dict)]
    return cleaned


def _whitelist_principle(principle: dict) -> dict:
    cleaned = {k: principle[k] for k in _ALLOWED_PRINCIPLE if k in principle}
    if "name" in cleaned and isinstance(cleaned["name"], str):
        cleaned["name"] = _truncate(cleaned["name"], _MAX_NAME)
    if "description" in cleaned and isinstance(cleaned["description"], str):
        cleaned["description"] = _truncate(cleaned["description"], _MAX_DESCRIPTION)
    if "requirements" in cleaned and isinstance(cleaned["requirements"], list):
        cleaned["requirements"] = [
            _whitelist_requirement(r) for r in cleaned["requirements"] if isinstance(r, dict)
        ]
    return cleaned


def validate_import(data: dict) -> dict:
    """Validate and sanitize an imported evaluator.

    Returns ``{"valid": True, "errors": [], "data": sanitized_dict}``
    on success, or ``{"valid": False, "errors": [...], "data": None}``
    on failure.
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

    if "principles" not in data:
        errors.append("Missing required field: principles")
    elif not isinstance(data["principles"], list):
        errors.append("Field 'principles' must be a list")
    else:
        for i, p in enumerate(data["principles"]):
            if not isinstance(p, dict):
                errors.append(f"Principle {i} must be an object")
                continue
            if not isinstance(p.get("name"), str) or not p["name"]:
                errors.append(f"Principle {i} missing required field: name")
            if "requirements" not in p:
                errors.append(f"Principle {i} missing required field: requirements")
            elif not isinstance(p["requirements"], list):
                errors.append(f"Principle {i} field 'requirements' must be a list")

    if errors:
        return {"valid": False, "errors": errors, "data": None}

    cleaned = {k: data[k] for k in _ALLOWED_TOP if k in data}
    if "name" in cleaned and isinstance(cleaned["name"], str):
        cleaned["name"] = _truncate(cleaned["name"], _MAX_NAME)
    if "description" in cleaned and isinstance(cleaned["description"], str):
        cleaned["description"] = _truncate(cleaned["description"], _MAX_DESCRIPTION)
    if isinstance(cleaned.get("principles"), list):
        cleaned["principles"] = [
            _whitelist_principle(p) for p in cleaned["principles"] if isinstance(p, dict)
        ]

    return {"valid": True, "errors": [], "data": cleaned}


def scan_text(text: str) -> list[str]:
    """Return injection warnings for arbitrary untrusted text (empty == clean)."""
    findings = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(f"suspicious content matches {pattern.pattern!r}")
    return findings


def scan_injection(data: dict) -> list[str]:
    """Scan all string fields for potential LLM injection patterns.

    Returns a list of human-readable warning strings.  Empty list means clean.
    """
    warnings: list[str] = []

    def _check(text: str, location: str) -> None:
        if not scan_text(text):
            return
        for pattern in _INJECTION_PATTERNS:
            m = pattern.search(text)
            if m:
                warnings.append(f"Suspicious text in {location}: contains '{m.group()}'")

    for field in ("name", "description", "source"):
        if isinstance(data.get(field), str):
            _check(data[field], f"standard {field}")

    for i, p in enumerate(data.get("principles", [])):
        if not isinstance(p, dict):
            continue
        for field in ("name", "description"):
            if isinstance(p.get(field), str):
                _check(p[field], f"principle '{p.get('name', i)}' {field}")
        for j, r in enumerate(p.get("requirements", [])):
            if not isinstance(r, dict):
                continue
            for field in ("text", "description"):
                if isinstance(r.get(field), str):
                    _check(r[field], f"principle '{p.get('name', i)}', requirement {j}")

    return warnings
