from datetime import datetime, timezone
from pathlib import Path

from quodeq.verifier.storage import (
    VerificationsStore,
    VerificationRecord,
)
from quodeq.verifier.models import Verdict


def _record(verification_id: str = "v1") -> VerificationRecord:
    return VerificationRecord(
        verification_id=verification_id,
        evaluation_id="eval-1",
        dimension="flexibility",
        finding_id="finding-42",
        verdict=Verdict.FALSE_POSITIVE,
        confidence=0.95,
        evidence_summary="ok",
        model="gemma4:e4b",
        elapsed_ms=1234,
        created_at=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_store_creates_db(tmp_path: Path):
    db = tmp_path / "verifications.db"
    store = VerificationsStore(db)
    assert db.exists()
    store.close()


def test_store_inserts_and_fetches(tmp_path: Path):
    store = VerificationsStore(tmp_path / "verifications.db")
    store.insert(_record())
    rec = store.get("v1")
    assert rec is not None
    assert rec.verdict == Verdict.FALSE_POSITIVE
    assert rec.dimension == "flexibility"
    assert rec.finding_id == "finding-42"
    store.close()


def test_store_get_returns_none_for_missing(tmp_path: Path):
    store = VerificationsStore(tmp_path / "verifications.db")
    assert store.get("missing") is None
    store.close()


def test_store_list_for_evaluation(tmp_path: Path):
    store = VerificationsStore(tmp_path / "verifications.db")
    store.insert(_record("v1"))
    store.insert(_record("v2"))
    rows = store.list_for_evaluation("eval-1")
    assert len(rows) == 2
    assert {r.verification_id for r in rows} == {"v1", "v2"}
    store.close()


def test_store_replace_updates_existing(tmp_path: Path):
    store = VerificationsStore(tmp_path / "verifications.db")
    r1 = _record("v1")
    store.insert(r1)
    r2 = VerificationRecord(
        verification_id="v1",
        evaluation_id="eval-1",
        dimension="flexibility",
        finding_id="finding-42",
        verdict=Verdict.CONFIRMED,
        confidence=0.5,
        evidence_summary="redo",
        model="gemma4:e4b",
        elapsed_ms=999,
        created_at=datetime(2026, 5, 11, 13, 0, 0, tzinfo=timezone.utc),
    )
    store.insert(r2)
    rec = store.get("v1")
    assert rec.verdict == Verdict.CONFIRMED
    assert rec.confidence == 0.5
    store.close()
