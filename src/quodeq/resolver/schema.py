"""SQL DDL for the symbol-index SQLite database.

One file = one source of truth for the schema. Bump SCHEMA_VERSION when
columns change so the index rebuilds instead of silently diverging.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_hashes (
    file       TEXT PRIMARY KEY,
    sha256     TEXT NOT NULL,
    language   TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classes (
    file       TEXT NOT NULL,
    line       INTEGER NOT NULL,
    name       TEXT NOT NULL,
    base_list  TEXT NOT NULL,    -- comma-separated identifiers
    language   TEXT NOT NULL,
    PRIMARY KEY (file, line, name)
);
CREATE INDEX IF NOT EXISTS classes_name_idx ON classes(name);
CREATE INDEX IF NOT EXISTS classes_base_idx ON classes(base_list);

CREATE TABLE IF NOT EXISTS functions (
    file        TEXT NOT NULL,
    line        INTEGER NOT NULL,
    name        TEXT NOT NULL,
    signature   TEXT NOT NULL,
    return_type TEXT,
    language    TEXT NOT NULL,
    PRIMARY KEY (file, line, name)
);
CREATE INDEX IF NOT EXISTS functions_name_idx ON functions(name);

CREATE TABLE IF NOT EXISTS function_params (
    file               TEXT NOT NULL,
    function_line      INTEGER NOT NULL,
    function_name      TEXT NOT NULL,
    param_name         TEXT NOT NULL,
    annotation_text    TEXT,                -- raw annotation as written
    annotation_names   TEXT NOT NULL,       -- comma-separated identifiers extracted from annotation
    language           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS function_params_annot_idx ON function_params(annotation_names);

CREATE TABLE IF NOT EXISTS imports (
    file          TEXT NOT NULL,
    line          INTEGER NOT NULL,
    imported_name TEXT NOT NULL,           -- the name as bound in this file
    source_module TEXT,                    -- "quodeq.services.base" for `from quodeq.services.base import X`
    is_lazy       INTEGER NOT NULL,        -- 1 if inside a function body, else 0
    language      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS imports_name_idx ON imports(imported_name);
CREATE INDEX IF NOT EXISTS imports_module_idx ON imports(source_module);

CREATE TABLE IF NOT EXISTS call_sites (
    file     TEXT NOT NULL,
    line     INTEGER NOT NULL,
    callee   TEXT NOT NULL,
    language TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS call_sites_callee_idx ON call_sites(callee);
"""
