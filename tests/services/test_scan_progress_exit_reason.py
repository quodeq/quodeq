"""scan_progress includes per-dim exit_reason when present in dimensions.json."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.scan_progress import build_scan_progress
from quodeq.shared.serialization import to_camel_dict


def _make_run(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "scan.json").write_text(json.dumps({"total_files": 100}), encoding="utf-8")
    run = project / "run"
    run.mkdir()
    return run


def test_scan_progress_includes_exit_reason(tmp_path):
    run = _make_run(tmp_path)
    (run / "status.json").write_text(json.dumps({
        "phase": "analyzing", "current_dimension": None,
        "started_at": "2026-05-23T08:00:00+00:00",
        "dimensions": ["security"],
    }), encoding="utf-8")
    (run / "dimensions.json").write_text(json.dumps({
        "dimensions": {"security": {"state": "done", "exit_reason": "time_limit"}},
    }), encoding="utf-8")
    (run / "security_evidence.jsonl").write_text("", encoding="utf-8")

    progress = build_scan_progress("job-1", run, time_limit_s=None)
    d = to_camel_dict(progress)
    security_dim = next(x for x in d["dimensions"] if x["id"] == "security")
    assert security_dim["exitReason"] == "time_limit"


def test_scan_progress_falls_back_to_incomplete_reason(tmp_path):
    """INCOMPLETE dims store the cause under `reason`, not `exit_reason`."""
    run = _make_run(tmp_path)
    (run / "status.json").write_text(json.dumps({
        "phase": "analyzing", "current_dimension": None,
        "started_at": "2026-05-23T08:00:00+00:00",
        "dimensions": ["security"],
    }), encoding="utf-8")
    (run / "dimensions.json").write_text(json.dumps({
        "dimensions": {"security": {"state": "incomplete", "reason": "provider_fatal"}},
    }), encoding="utf-8")
    (run / "security_evidence.jsonl").write_text("", encoding="utf-8")

    progress = build_scan_progress("job-1", run, time_limit_s=None)
    d = to_camel_dict(progress)
    security_dim = next(x for x in d["dimensions"] if x["id"] == "security")
    assert security_dim["exitReason"] == "provider_fatal"


def test_scan_progress_includes_run_level_exit_reason(tmp_path):
    run = _make_run(tmp_path)
    (run / "status.json").write_text(json.dumps({
        "state": "failed", "exit_reason": "provider_fatal",
        "phase": "analyzing", "current_dimension": None,
        "started_at": "2026-05-23T08:00:00+00:00",
        "dimensions": ["security"],
    }), encoding="utf-8")

    progress = build_scan_progress("job-1", run, time_limit_s=None)
    d = to_camel_dict(progress)
    assert d["exitReason"] == "provider_fatal"


def test_scan_progress_omits_exit_reason_when_absent(tmp_path):
    run = _make_run(tmp_path)
    (run / "status.json").write_text(json.dumps({
        "phase": "analyzing", "current_dimension": None,
        "started_at": "2026-05-23T08:00:00+00:00",
        "dimensions": ["security"],
    }), encoding="utf-8")
    (run / "dimensions.json").write_text(json.dumps({
        "dimensions": {"security": {"state": "done"}},
    }), encoding="utf-8")
    (run / "security_evidence.jsonl").write_text("", encoding="utf-8")

    progress = build_scan_progress("job-1", run, time_limit_s=None)
    d = to_camel_dict(progress)
    security_dim = next(x for x in d["dimensions"] if x["id"] == "security")
    assert security_dim.get("exitReason") is None
