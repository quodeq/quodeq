"""Tests for the publish staging logic (pure file operations)."""
import json
from pathlib import Path

from quodeq.services.shared_publish import (
    copy_run,
    list_completed_runs,
    merge_actions_log,
    stage_project,
)


def _make_run(project_dir: Path, run_id: str, state: str) -> Path:
    run = project_dir / run_id
    (run / "evidence").mkdir(parents=True)
    (run / "status.json").write_text(json.dumps({"state": state, "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text('{"event_type":"RUN_STARTED"}\n')
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "evidence" / "security_evidence.jsonl").write_text("{}\n")
    (run / "run.log").write_text("noise")            # must NOT be copied
    (run / "evaluation.db").write_text("derived")     # must NOT be copied
    return run


def test_list_completed_runs_filters_terminal_done_only(tmp_path):
    _make_run(tmp_path, "r-done", "done")
    _make_run(tmp_path, "r-running", "running")
    _make_run(tmp_path, "r-failed", "failed")
    (tmp_path / "not-a-run").mkdir()  # no status.json
    runs = list_completed_runs(tmp_path)
    assert [r.name for r in runs] == ["r-done"]


def test_copy_run_applies_allowlist(tmp_path):
    src = _make_run(tmp_path / "src", "r1", "done")
    dest = tmp_path / "dest" / "r1"
    copy_run(src, dest)
    assert (dest / "status.json").exists()
    assert (dest / "dimensions.json").exists()
    assert (dest / "events.jsonl").exists()
    assert (dest / "evidence" / "manifest.json").exists()
    assert (dest / "evidence" / "security_evidence.jsonl").exists()
    assert not (dest / "run.log").exists()
    assert not (dest / "evaluation.db").exists()


def test_merge_actions_log_unions_and_sorts(tmp_path):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    dest = tmp_path / "merged.jsonl"
    line1 = '{"event_id":"1","timestamp":"2026-07-01T10:00:00Z","event_type":"FINDING_DISMISSED","payload":{}}'
    line2 = '{"event_id":"2","timestamp":"2026-07-02T10:00:00Z","event_type":"FINDING_DISMISSED","payload":{}}'
    a.write_text(line2 + "\n" + line1 + "\n")
    b.write_text(line1 + "\n")  # duplicate of line1
    merge_actions_log(a, b, dest)
    lines = dest.read_text().splitlines()
    assert lines == [line1, line2]


def test_merge_actions_log_missing_inputs(tmp_path):
    dest = tmp_path / "merged.jsonl"
    merge_actions_log(tmp_path / "none1", tmp_path / "none2", dest)
    assert not dest.exists() or dest.read_text() == ""


def test_stage_project_copies_info_actions_and_done_runs(tmp_path):
    project = tmp_path / "local" / "proj-uuid"
    project.mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"x"}')
    (project / "actions.jsonl").write_text('{"event_id":"1","timestamp":"t"}\n')
    _make_run(project, "r-done", "done")
    _make_run(project, "r-live", "running")
    dest = tmp_path / "clone" / "evaluations" / "proj-uuid"
    count = stage_project(project, dest)
    assert count == 1
    assert (dest / "repository_info.json").exists()
    assert (dest / "actions.jsonl").exists()
    assert (dest / "r-done" / "status.json").exists()
    assert not (dest / "r-live").exists()


def test_list_completed_runs_skips_unsupported_schema_version(tmp_path):
    """A run with schema_version > supported should be skipped, not crash."""
    run = tmp_path / "r-unsupported"
    (run / "evidence").mkdir(parents=True)
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 99}))
    _make_run(tmp_path, "r-done", "done")
    runs = list_completed_runs(tmp_path)
    # Only the valid "done" run should be included; the unsupported one should be skipped
    assert [r.name for r in runs] == ["r-done"]
