"""Schema validation for dimensions JSON files."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import jsonschema

from quodeq.shared.utils import read_json

_SCHEMAS_DIR = Path(__file__).parent / "schemas"
_SCHEMA_CACHE_SIZE = 32


@lru_cache(maxsize=_SCHEMA_CACHE_SIZE)
def _load_schema(name: str) -> dict:
    """Load and return the JSON schema file identified by *name*."""
    path = _SCHEMAS_DIR / name
    try:
        return read_json(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load schema {path.name}") from exc


@lru_cache(maxsize=_SCHEMA_CACHE_SIZE)
def _get_validator(schema_file: str) -> jsonschema.Draft202012Validator:
    """Return a cached JSON Schema validator for *schema_file*."""
    schema = _load_schema(schema_file)
    return jsonschema.Draft202012Validator(schema)


def clear_schema_cache() -> None:
    """Clear the schema and validator LRU caches. Useful for test isolation."""
    _load_schema.cache_clear()
    _get_validator.cache_clear()


def validate_dimensions(data: dict) -> list[str]:
    """Validate dimensions.json data."""
    return _validate(data, "dimensions_schema.json")


def _validate(data: dict, schema_file: str) -> list[str]:
    """Validate *data* against *schema_file* and return error messages."""
    validator = _get_validator(schema_file)
    return [e.message for e in validator.iter_errors(data)]
