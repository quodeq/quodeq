"""Private helper functions for type-safe extraction from raw dicts."""

from __future__ import annotations


def get_opt_str(v: object) -> str | None:
    return v if isinstance(v, str) else None


def get_opt_int(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def get_opt_float(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def get_opt_str_or_int(v: object) -> int | str | None:
    if isinstance(v, bool):
        return None
    return v if isinstance(v, (str, int)) else None


def get_str(raw: dict[str, object], key: str, default: str = "") -> str:
    v = raw.get(key, default)
    return v if isinstance(v, str) else default


def get_int(raw: dict[str, object], key: str, default: int = 0) -> int:
    v = raw.get(key, default)
    if isinstance(v, bool):
        return default
    return v if isinstance(v, int) else default


def get_bool(raw: dict[str, object], key: str, default: bool = False) -> bool:
    v = raw.get(key, default)
    return v if isinstance(v, bool) else default


def get_str_list(raw: dict[str, object], key: str) -> list[str]:
    v = raw.get(key)
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str)]


def require_str(raw: dict[str, object], field_name: str, context: str = "") -> str:
    """Return raw[field_name] as str, or raise TypeError with a descriptive message."""
    value = raw.get(field_name)
    if not isinstance(value, str):
        prefix = f"{context}." if context else ""
        msg = f"{prefix}{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    return value
