"""SQLite-backed storage for verifier results.

Each evaluation gets its own verifications.db at
`~/.quodeq/evaluations/<eval_id>/verifications.db`. The schema is intentionally
small — verdict + a few audit fields. Heavy artifacts (manifest, prompt, raw
response) live in the audit-log directory, not in this DB.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from quodeq.verifier.models import Verdict


SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS verifications (
    verification_id TEXT PRIMARY KEY,
    evaluation_id   TEXT NOT NULL,
    dimension       TEXT NOT NULL,
    finding_id      TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    confidence      REAL NOT NULL,
    evidence_summary TEXT NOT NULL,
    model           TEXT NOT NULL,
    elapsed_ms      INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verifications_eval_idx ON verifications(evaluation_id);
CREATE INDEX IF NOT EXISTS verifications_finding_idx ON verifications(dimension, finding_id);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class VerificationRecord:
    verification_id: str
    evaluation_id: str
    dimension: str
    finding_id: str
    verdict: Verdict
    confidence: float
    evidence_summary: str
    model: str
    elapsed_ms: int
    created_at: datetime


class VerificationsStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(DDL)
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def insert(self, record: VerificationRecord) -> None:
        self.conn.execute(
            "INSERT INTO verifications("
            "verification_id, evaluation_id, dimension, finding_id, "
            "verdict, confidence, evidence_summary, model, elapsed_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(verification_id) DO UPDATE SET "
            "verdict=excluded.verdict, confidence=excluded.confidence, "
            "evidence_summary=excluded.evidence_summary, "
            "model=excluded.model, elapsed_ms=excluded.elapsed_ms, "
            "created_at=excluded.created_at",
            (
                record.verification_id,
                record.evaluation_id,
                record.dimension,
                record.finding_id,
                record.verdict.value,
                record.confidence,
                record.evidence_summary,
                record.model,
                record.elapsed_ms,
                record.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get(self, verification_id: str) -> VerificationRecord | None:
        row = self.conn.execute(
            "SELECT * FROM verifications WHERE verification_id = ?",
            (verification_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_for_evaluation(self, evaluation_id: str) -> list[VerificationRecord]:
        rows = self.conn.execute(
            "SELECT * FROM verifications WHERE evaluation_id = ? "
            "ORDER BY created_at DESC",
            (evaluation_id,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> VerificationRecord:
        return VerificationRecord(
            verification_id=row["verification_id"],
            evaluation_id=row["evaluation_id"],
            dimension=row["dimension"],
            finding_id=row["finding_id"],
            verdict=Verdict(row["verdict"]),
            confidence=row["confidence"],
            evidence_summary=row["evidence_summary"],
            model=row["model"],
            elapsed_ms=row["elapsed_ms"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
