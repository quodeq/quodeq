"""DDL strings for evaluation.db. Constants only — no logic."""
from __future__ import annotations

EVALUATION_DDL = """
PRAGMA user_version = 1;

CREATE TABLE findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version  INTEGER NOT NULL DEFAULT 1,
    practice_id     TEXT NOT NULL,
    dimension       TEXT NOT NULL DEFAULT '',
    requirement     TEXT,
    verdict         TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
    severity        TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','minor')),
    file            TEXT NOT NULL DEFAULT '',
    line            INTEGER NOT NULL DEFAULT 0,
    end_line        INTEGER NOT NULL DEFAULT 0,
    title           TEXT NOT NULL DEFAULT '',
    reason          TEXT NOT NULL DEFAULT '',
    snippet         TEXT NOT NULL DEFAULT '',
    violation_type  TEXT NOT NULL DEFAULT '',
    context         TEXT NOT NULL DEFAULT '',
    scope           TEXT NOT NULL DEFAULT '',
    req_refs_json   TEXT,
    dedup_key       TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_findings_dimension   ON findings(dimension);
CREATE INDEX idx_findings_severity    ON findings(severity);
CREATE INDEX idx_findings_verdict     ON findings(verdict);
CREATE INDEX idx_findings_file        ON findings(file);
CREATE INDEX idx_findings_requirement ON findings(requirement);
CREATE INDEX idx_findings_practice    ON findings(practice_id);

CREATE VIRTUAL TABLE findings_fts USING fts5(
    reason, snippet,
    content='findings', content_rowid='id', tokenize='porter'
);

CREATE TRIGGER findings_ai AFTER INSERT ON findings BEGIN
    INSERT INTO findings_fts(rowid, reason, snippet)
    VALUES (new.id, new.reason, new.snippet);
END;
CREATE TRIGGER findings_ad AFTER DELETE ON findings BEGIN
    INSERT INTO findings_fts(findings_fts, rowid, reason, snippet)
    VALUES ('delete', old.id, old.reason, old.snippet);
END;
CREATE TRIGGER findings_au AFTER UPDATE ON findings BEGIN
    INSERT INTO findings_fts(findings_fts, rowid, reason, snippet)
    VALUES ('delete', old.id, old.reason, old.snippet);
    INSERT INTO findings_fts(rowid, reason, snippet)
    VALUES (new.id, new.reason, new.snippet);
END;

CREATE TABLE dimension_scores (
    dimension       TEXT PRIMARY KEY,
    score           REAL,
    grade           TEXT,
    confidence      TEXT,
    files_read      INTEGER NOT NULL DEFAULT 0,
    source_count    INTEGER NOT NULL DEFAULT 0,
    coverage_pct    REAL NOT NULL DEFAULT 0.0,
    completed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE run_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
"""

SCHEMA_VERSION = 1
