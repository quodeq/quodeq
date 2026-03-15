"""Schema validation for plugin and dimensions JSON files."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import jsonschema

_SCHEMAS_DIR = Path(__file__).parent / "schemas"
_SCHEMA_CACHE_SIZE = 32


@lru_cache(maxsize=_SCHEMA_CACHE_SIZE)
def _load_schema(name: str) -> dict:
    path = _SCHEMAS_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load schema {path}: {exc}") from exc


@lru_cache(maxsize=_SCHEMA_CACHE_SIZE)
def _get_validator(schema_file: str) -> jsonschema.Draft202012Validator:
    schema = _load_schema(schema_file)
    return jsonschema.Draft202012Validator(schema)


def validate_plugin(data: dict) -> list[str]:
    """Validate plugin.json data. Returns list of error messages (empty = valid)."""
    return _validate(data, "plugin_schema.json")


def validate_dimensions(data: dict) -> list[str]:
    """Validate dimensions.json data."""
    return _validate(data, "dimensions_schema.json")


def validate_plugin_dir(plugin_dir: Path) -> dict[str, list[str]]:
    """Validate all JSON files in a plugin directory.

    Returns a dict mapping filename to list of errors.
    Only files with errors appear in the result.
    """
    errors: dict[str, list[str]] = {}

    validators = {
        "plugin.json": validate_plugin,
        "dimensions.json": validate_dimensions,
    }

    for filename, validator_fn in validators.items():
        filepath = plugin_dir / filename
        if not filepath.exists():
            errors[filename] = [f"{filename} not found"]
            continue
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors[filename] = [f"Cannot read {filename}: {exc}"]
            continue
        file_errors = validator_fn(data)
        if file_errors:
            errors[filename] = file_errors

    return errors


def _validate(data: dict, schema_file: str) -> list[str]:
    validator = _get_validator(schema_file)
    return [e.message for e in validator.iter_errors(data)]
