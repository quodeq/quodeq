"""Tests for JobSnapshot serialisation, focusing on provider/model fields."""
from __future__ import annotations

from quodeq.core.types.job import JobSnapshot
from quodeq.core.types._serialization import to_camel_dict


def test_job_snapshot_serialises_provider_and_model():
    snap = JobSnapshot(
        job_id="ext-abc",
        status="running",
        ai_provider="llamacpp",
        ai_model="qwen3.6-27b",
    )
    payload = to_camel_dict(snap)
    assert payload["aiProvider"] == "llamacpp"
    assert payload["aiModel"] == "qwen3.6-27b"


def test_job_snapshot_omits_provider_and_model_when_none():
    snap = JobSnapshot(job_id="ext-abc", status="running")
    payload = to_camel_dict(snap)
    assert "aiProvider" not in payload
    assert "aiModel" not in payload
