"""Dataclass-to-camelCase-dict serialization utilities."""
from __future__ import annotations

import dataclasses
import re

_CAMEL_RE = re.compile(r"_([a-z])")


def _to_camel(name: str) -> str:
    return _CAMEL_RE.sub(lambda m: m.group(1).upper(), name)


def to_camel_dict(obj: object) -> object:
    """Recursively convert a frozen dataclass to a camelCase dict."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            _to_camel(f.name): to_camel_dict(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
            if getattr(obj, f.name) is not None  # omit None fields
        }
    if isinstance(obj, list):
        return [to_camel_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_camel_dict(v) for k, v in obj.items()}
    return obj
