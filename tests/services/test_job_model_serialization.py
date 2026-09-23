"""Tests for _job_file_store.py: Job JSON serialization round-trip."""

from __future__ import annotations


from quodeq.services._job_model import Job
from quodeq.services._job_file_store import _job_to_json, _job_from_json
from quodeq.core.run.job_status import JobStatus


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_round_trip(self):
        original = Job(
            job_id="j99",
            status="completed",
            command=["python", "run.py"],
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T01:00:00Z",
            exit_code=0,
            output_project="proj",
            output_run_id="run1",
            phase="scoring",
            current_dimension="security",
            dimensions=["security", "performance"],
        )
        original.logs.append("log line 1")
        data = _job_to_json(original)
        restored = _job_from_json(data)
        assert restored.job_id == original.job_id
        assert restored.status == original.status
        assert restored.command == original.command
        assert restored.exit_code == original.exit_code
        assert list(restored.logs) == list(original.logs)
        assert restored.output_project == original.output_project
        assert restored.dimensions == original.dimensions

    def test_from_json_missing_optional_fields(self):
        data = {"job_id": "j1", "status": "running"}
        job = _job_from_json(data)
        assert job.command == []
        assert job.started_at == ""
        assert job.ended_at is None
        assert job.exit_code is None
        assert list(job.logs) == []

    def test_to_json_contains_all_keys(self):
        job = Job("j1", "running", ["cmd"], "now", None, None)
        data = _job_to_json(job)
        expected_keys = {
            "job_id", "status", "command", "started_at", "ended_at",
            "exit_code", "logs", "output_project", "output_run_id",
            "phase", "deadline_at", "current_dimension", "dimensions",
            "ai_provider", "ai_model", "time_limit_s", "exit_reason",
        }
        assert set(data.keys()) == expected_keys

    def test_job_round_trips_provider_and_model(self):
        job = Job(
            job_id="job-1",
            status="running",
            command=["x"],
            started_at="2026-01-01T00:00:00Z",
            ended_at=None,
            exit_code=None,
            ai_provider="ollama",
            ai_model="gemma4:26b-mlx",
        )
        blob = _job_to_json(job)
        assert blob["ai_provider"] == "ollama"
        assert blob["ai_model"] == "gemma4:26b-mlx"
        restored = _job_from_json(blob)
        assert restored.ai_provider == "ollama"
        assert restored.ai_model == "gemma4:26b-mlx"

    def test_job_defaults_provider_and_model_to_none(self):
        job = Job(
            job_id="job-1",
            status="running",
            command=["x"],
            started_at="2026-01-01T00:00:00Z",
            ended_at=None,
            exit_code=None,
        )
        blob = _job_to_json(job)
        blob.pop("ai_provider", None)
        blob.pop("ai_model", None)
        restored = _job_from_json(blob)
        assert restored.ai_provider is None
        assert restored.ai_model is None

    def test_to_dict_carries_provider_and_model(self):
        job = Job(
            job_id="job-1", status="running", command=["x"],
            started_at="2026-01-01T00:00:00Z", ended_at=None, exit_code=None,
            ai_provider="ollama", ai_model="gemma4:26b-mlx",
        )
        snap = job.to_dict()
        assert snap.ai_provider == "ollama"
        assert snap.ai_model == "gemma4:26b-mlx"


class TestStatusParsing:
    def test_known_status_is_parsed_to_the_member(self):
        job = _job_from_json({"job_id": "j1", "status": "done"})
        assert job.status is JobStatus.DONE

    def test_unknown_status_is_kept_raw_with_a_warning(self, caplog):
        with caplog.at_level("WARNING"):
            job = _job_from_json({"job_id": "j1", "status": "completed"})
        assert job.status == "completed"
        assert not isinstance(job.status, JobStatus)
        assert "completed" in caplog.text
