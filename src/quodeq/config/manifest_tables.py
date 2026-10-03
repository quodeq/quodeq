"""Shared steps of the manifest parsers: read a TOML document, collect dependency keys."""
from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping


def toml_table(content: str) -> dict | None:
    """*content* parsed as TOML, or None when it is not valid TOML."""
    try:
        return tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return None


def lowered_keys(table: Mapping, keys: Iterable[str]) -> set[str]:
    """Lower-cased string keys of every mapping stored under one of *keys* in *table*.

    Missing keys and values that are not mappings contribute nothing.
    """
    names: set[str] = set()
    for key in keys:
        value = table.get(key)
        if isinstance(value, dict):
            names.update(k.lower() for k in value if isinstance(k, str))
    return names
