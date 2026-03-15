"""Shared helpers for action API modules."""
from __future__ import annotations

from typing import Any


def error_response(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    """Build a standardized error response tuple for Flask endpoints."""
    return {"error": message, "code": code}, status


def validate_evaluation_payload(payload: dict[str, Any]) -> str | None:
    """Validate the evaluate request payload.

    Returns an error message string if validation fails, or ``None`` if valid.
    Required fields: ``repo`` (non-empty string).
    Optional typed fields: ``discipline`` (str), ``dimensions`` (str),
    ``numerical`` (bool), ``aiCmd`` (str), ``aiModel`` (str),
    ``subagentModel`` (str).
    """
    missing: list[str] = []
    invalid: list[str] = []

    repo = payload.get("repo")
    if not repo:
        missing.append("repo")
    elif not isinstance(repo, str):
        invalid.append("repo (must be a string)")

    # dimensions accepts both string ("a,b") and array (["a","b"]) from frontend
    dims = payload.get("dimensions")
    if dims is not None:
        if isinstance(dims, list):
            payload["dimensions"] = ",".join(str(d) for d in dims)
        elif not isinstance(dims, str):
            invalid.append("dimensions (must be a string or array of strings)")

    str_fields = ("discipline", "aiCmd", "aiModel", "subagentModel")
    for field in str_fields:
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            invalid.append(f"{field} (must be a string)")

    numerical = payload.get("numerical")
    if numerical is not None and not isinstance(numerical, bool):
        invalid.append("numerical (must be a boolean)")

    parts: list[str] = []
    if missing:
        parts.append(f"missing required fields: {', '.join(missing)}")
    if invalid:
        parts.append(f"invalid fields: {', '.join(invalid)}")
    return "; ".join(parts) if parts else None
