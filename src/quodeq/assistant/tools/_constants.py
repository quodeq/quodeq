"""Shared constants for the assistant.tools package."""
from __future__ import annotations

# JSON Schema "type" values, repeated across several tools' parameter specs.
JSON_SCHEMA_TYPE_OBJECT = "object"
JSON_SCHEMA_TYPE_STRING = "string"

# Positional decode()/encode() calls that don't already self-document via an
# encoding= keyword. A separate copy from assistant/_constants.py's own
# ENCODING_UTF8: check_private_imports.py's rule B requires importers of a
# private _constants module to live in the directory that owns it, and this
# package (assistant/tools/) is not that directory.
ENCODING_UTF8 = "utf-8"
