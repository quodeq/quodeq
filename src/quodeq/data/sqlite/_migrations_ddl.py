"""DDL constants for incremental schema upgrades in :mod:`_migrations`.

Split out of ``_migrations.py`` purely to keep that module's upgrade
functions under the size cap; each constant here is executed verbatim via
``conn.executescript`` by its corresponding ``_upgrade_*`` function.
"""
from __future__ import annotations

# Rebuild of the `findings` table used by `_upgrade_v3_to_v4` to widen the
# severity CHECK constraint (SQLite cannot ALTER a CHECK in place).
_V4_REBUILD_DDL = """
    -- Drop triggers and FTS index that reference the old table by name.
    DROP TRIGGER IF EXISTS findings_ai;
    DROP TRIGGER IF EXISTS findings_ad;
    DROP TRIGGER IF EXISTS findings_au;
    DROP TABLE IF EXISTS findings_fts;

    ALTER TABLE findings RENAME TO findings_old_v3;

    CREATE TABLE findings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        schema_version  INTEGER NOT NULL DEFAULT 1,
        practice_id     TEXT NOT NULL,
        dimension       TEXT NOT NULL DEFAULT '',
        requirement     TEXT,
        verdict         TEXT NOT NULL CHECK (verdict IN ('violation','compliance','dismissed')),
        severity        TEXT NOT NULL CHECK (severity IN ('critical','major','high','medium','low','minor')),
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
        confidence      INTEGER NOT NULL DEFAULT 100,
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    );

    INSERT INTO findings (
        id, schema_version, practice_id, dimension, requirement, verdict,
        severity, file, line, end_line, title, reason, snippet,
        violation_type, context, scope, req_refs_json, dedup_key,
        confidence, created_at
    )
    SELECT
        id, schema_version, practice_id, dimension, requirement, verdict,
        severity, file, line, end_line, title, reason, snippet,
        violation_type, context, scope, req_refs_json, dedup_key,
        confidence, created_at
    FROM findings_old_v3;

    DROP TABLE findings_old_v3;

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

    -- Backfill FTS for any rows copied over.
    INSERT INTO findings_fts(rowid, reason, snippet)
        SELECT id, reason, snippet FROM findings;

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
"""
