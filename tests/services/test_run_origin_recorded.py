"""The CLI records where a run came from, and an index-served job carries it."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.config.ci_env import current_run_origin
from quodeq.core.run.origin import RunOrigin
from quodeq.data.fs.run_status_store import RunState, RunStatus, read_status, write_status
from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.services.wiring import run_index

_PR = RunOrigin(kind="ci", event="pull_request", pr=1402, pr_url="https://github.com/quodeq/quodeq/pull/1402")


def test_status_json_keeps_the_origin(tmp_path: Path) -> None:
    write_status(tmp_path, RunStatus(state=RunState.RUNNING, job_id="ext-r", started_at="t", dimensions=[], origin=_PR))
    assert RunStatus.from_status_dict(read_status(tmp_path)).origin == _PR


def test_the_cli_reads_github_actions(tmp_path: Path, monkeypatch) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 1402}}))
    for k, v in {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event),
                 "GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "quodeq/quodeq"}.items():
        monkeypatch.setenv(k, v)
    assert current_run_origin().pr_url == "https://github.com/quodeq/quodeq/pull/1402"


def test_an_unreadable_event_file_still_gives_a_ci_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "missing.json"))
    origin = current_run_origin()
    assert origin.kind == "ci" and origin.pr is None


def test_an_index_served_job_carries_the_origin(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    run = reports / "proj" / "r1"
    run.mkdir(parents=True)
    write_status(run, RunStatus(state=RunState.RUNNING, job_id="ext-r1", started_at="t", dimensions=["security"], origin=_PR))
    db = run_index.open_index(tmp_path / "idx.db")
    try:
        run_index.sync_index_for_run(db, run)
    finally:
        db.close()
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db", reports_root=reports)
    assert provider.get_evaluation_status("ext-r1", reports_dir=str(reports)).origin == _PR
