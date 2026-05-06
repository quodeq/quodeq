import json
import os
import sys
from pathlib import Path

from quodeq.services.base import EvaluationOptions
from quodeq.services.filesystem import FilesystemActionProvider


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class StubJobs:
    """Minimal job manager stub that captures the command passed to start_job."""

    def __init__(self):
        self.captured: dict = {}

    def start_job(self, cmd, cwd, env):
        self.captured["cmd"] = cmd
        self.captured["cwd"] = cwd
        self.captured["env"] = env
        return {"jobId": "test"}


def test_list_projects_returns_latest_run(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "proj" / "20260101" / "evaluation" / "maintainability.json",
        {
            "dimension": "maintainability",
            "overallScore": "5/10",
            "overallGrade": "Adequate",
        },
    )
    (reports / "proj" / "20260101" / "evidence").mkdir(parents=True, exist_ok=True)
    (reports / "proj" / "20260101" / "evidence" / "manifest.json").write_text("{}")
    (reports / "proj" / "20260101" / "scan.json").write_text("{}")
    _write_json(
        reports / "proj" / "20260102" / "evaluation" / "maintainability.json",
        {
            "dimension": "maintainability",
            "overallScore": "6/10",
            "overallGrade": "Good",
        },
    )
    (reports / "proj" / "20260102" / "evidence").mkdir(parents=True, exist_ok=True)
    (reports / "proj" / "20260102" / "evidence" / "manifest.json").write_text("{}")
    (reports / "proj" / "20260102" / "scan.json").write_text("{}")

    provider = FilesystemActionProvider()
    result = provider.list_projects(str(reports))

    assert result["projects"], "expected projects to be listed"
    project = result["projects"][0]
    assert project["name"] == "proj"
    assert project["runsCount"] == 2
    assert project["latestRunId"] == "20260102"
    assert project["latestDate"] == "2026-01-02"


def test_get_dimension_eval_from_json(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "proj" / "20260102" / "evaluation" / "maintainability.json",
        {
            "dimension": "maintainability",
            "overallScore": "4/10",
            "overallGrade": "Poor",
            "principles": [
                {"name": "Separation of Concerns", "score": "4/10", "grade": "Poor"}
            ],
        },
    )

    provider = FilesystemActionProvider()
    payload = provider.get_dimension_eval(str(reports), "proj", "20260102", "maintainability")

    assert payload["dimension"] == "maintainability"
    grades = payload["principleGrades"]
    assert any(item["principle"] == "Overall" for item in grades)
    assert any(item["principle"] == "Separation of Concerns" for item in grades)


def test_browse_repo_filters_hidden(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "visible").mkdir()
    (tmp_path / ".hidden").mkdir()

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    provider = FilesystemActionProvider()
    payload = provider.browse_repo(str(tmp_path))

    names = [entry["name"] for entry in payload["directories"]]
    assert "visible" in names
    assert ".hidden" not in names


def test_start_evaluation_uses_cli_module(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    reports_dir = tmp_path / "reports"

    jobs = StubJobs()
    provider = FilesystemActionProvider(job_manager=jobs)

    provider.start_evaluation(
        repo=str(repo_path),
        reports_dir=str(reports_dir),
        options=EvaluationOptions(),
    )

    assert jobs.captured["cmd"][:5] == [
        sys.executable,
        "-m",
        "quodeq.cli",
        "evaluate",
        str(repo_path.resolve()),
    ]
    assert "-o" in jobs.captured["cmd"]
    idx = jobs.captured["cmd"].index("-o")
    assert jobs.captured["cmd"][idx + 1] == str(reports_dir.resolve())


def test_start_evaluation_always_passes_absolute_reports_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    jobs = StubJobs()
    provider = FilesystemActionProvider(job_manager=jobs)

    provider.start_evaluation(
        repo=str(repo_path),
        reports_dir="reports",
        options=EvaluationOptions(),
    )

    assert "-o" in jobs.captured["cmd"]
    idx = jobs.captured["cmd"].index("-o")
    assert Path(jobs.captured["cmd"][idx + 1]).is_absolute()


def test_start_evaluation_writes_repository_info(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    reports_dir = tmp_path / "reports"

    provider = FilesystemActionProvider(job_manager=StubJobs())

    provider.start_evaluation(
        repo=str(repo_path),
        reports_dir=str(reports_dir),
        options=EvaluationOptions(discipline="cli_bash"),
    )

    # UUID-based project directory — find the created project dir
    project_dirs = [d for d in reports_dir.iterdir() if d.is_dir()]
    assert len(project_dirs) == 1
    info_path = project_dirs[0] / "repository_info.json"
    payload = json.loads(info_path.read_text())
    assert payload["name"] == "repo"
    assert payload["discipline"] == "cli_bash"
    assert payload["location"] == "local"
    assert payload["path"] == str(repo_path.resolve())
    assert "uuid" in payload


def test_start_evaluation_writes_repository_info_for_online_repo(tmp_path: Path) -> None:
    repo_url = "git@github.com:example/acme-service.git"
    reports_dir = tmp_path / "reports"

    provider = FilesystemActionProvider(job_manager=StubJobs())

    provider.start_evaluation(
        repo=repo_url,
        reports_dir=str(reports_dir),
        options=EvaluationOptions(discipline="backend_springboot_java"),
    )

    # UUID-based project directory
    project_dirs = [d for d in reports_dir.iterdir() if d.is_dir()]
    assert len(project_dirs) == 1
    info_path = project_dirs[0] / "repository_info.json"
    payload = json.loads(info_path.read_text())
    assert payload["name"] == "acme-service"
    assert payload["discipline"] == "backend_springboot_java"
    assert payload["location"] == "online"
    assert payload["path"] == repo_url
    assert "uuid" in payload


def test_get_evaluation_status_external_surfaces_deadline_at(tmp_path: Path) -> None:
    """External (CLI / ext-prefixed) runs must surface deadline_at on the snapshot.

    The dashboard's countdown timer reads ``job.deadlineAt`` to render a
    live ticker. Internal runs get this populated via the ``analyzing_start``
    marker parsed by JobManager. External runs bypass JobManager, so the
    snapshot builder must read deadline_at from the run's status.json.
    """
    reports = tmp_path / "reports"
    project_uuid = "11111111-2222-3333-4444-555555555555"
    run_id = "20260101120000"
    run_dir = reports / project_uuid / run_id
    run_dir.mkdir(parents=True)

    # A real run is signalled by the evidence/manifest.json file. Without it
    # the index sync skips the directory.
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "manifest.json").write_text("{}")

    deadline_iso = "2026-01-01T12:05:00+00:00"
    _write_json(
        run_dir / "status.json",
        {
            "schema_version": 1,
            "job_id": f"ext-{run_id}",
            "state": "running",
            "started_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:30+00:00",
            "finalized_at": None,
            "phase": "analyzing",
            "current_dimension": "reliability",
            "dimensions": ["reliability"],
            # Use the test process's own PID so the stale-promotion check
            # (heartbeat fresh + PID alive) treats this as a live run and
            # does NOT rewrite status.json without the deadline.
            "pid": os.getpid(),
            "exit_reason": None,
            "deadline_at": deadline_iso,
        },
    )
    # Fresh heartbeat — the stale check requires < 30s since last heartbeat.
    (run_dir / ".heartbeat").write_text("")

    provider = FilesystemActionProvider()
    snapshot = provider.get_evaluation_status(f"ext-{run_id}", reports_dir=reports)

    assert snapshot is not None
    assert snapshot.job_id == f"ext-{run_id}"
    assert snapshot.deadline_at == deadline_iso
    assert snapshot.source == "external"


def test_get_evaluation_status_external_handles_missing_deadline(tmp_path: Path) -> None:
    """Snapshot builder must tolerate runs that have no deadline (unlimited budget)."""
    reports = tmp_path / "reports"
    project_uuid = "11111111-2222-3333-4444-555555555555"
    run_id = "20260101120000"
    run_dir = reports / project_uuid / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "manifest.json").write_text("{}")

    _write_json(
        run_dir / "status.json",
        {
            "schema_version": 1,
            "job_id": f"ext-{run_id}",
            "state": "running",
            "started_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:30+00:00",
            "finalized_at": None,
            "phase": "analyzing",
            "current_dimension": None,
            "dimensions": ["reliability"],
            "pid": os.getpid(),
            "exit_reason": None,
            # no deadline_at field — unlimited budget
        },
    )
    (run_dir / ".heartbeat").write_text("")

    provider = FilesystemActionProvider()
    snapshot = provider.get_evaluation_status(f"ext-{run_id}", reports_dir=reports)

    assert snapshot is not None
    assert snapshot.deadline_at is None
