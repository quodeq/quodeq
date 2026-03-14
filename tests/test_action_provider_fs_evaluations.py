from pathlib import Path
import json
import sys

from quodeq.provider.base import EvaluationOptions
from quodeq.provider.filesystem import FilesystemActionProvider


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


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
    _write_json(
        reports / "proj" / "20260102" / "evaluation" / "maintainability.json",
        {
            "dimension": "maintainability",
            "overallScore": "6/10",
            "overallGrade": "Good",
        },
    )

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


def test_browse_repo_filters_hidden(tmp_path: Path) -> None:
    (tmp_path / "visible").mkdir()
    (tmp_path / ".hidden").mkdir()

    provider = FilesystemActionProvider()
    payload = provider.browse_repo(str(tmp_path))

    names = [entry["name"] for entry in payload["directories"]]
    assert "visible" in names
    assert ".hidden" not in names


def test_start_evaluation_uses_cli_module(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    reports_dir = tmp_path / "reports"

    captured = {}

    class StubJobs:
        def start_job(self, cmd, cwd, env):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["env"] = env
            return {"jobId": "test"}

    provider = FilesystemActionProvider(job_manager=StubJobs())

    provider.start_evaluation(
        repo=str(repo_path),
        reports_dir=str(reports_dir),
        options=EvaluationOptions(),
    )

    assert captured["cmd"][:5] == [
        sys.executable,
        "-m",
        "quodeq.cli",
        "evaluate",
        str(repo_path.resolve()),
    ]
    assert "-o" in captured["cmd"]
    idx = captured["cmd"].index("-o")
    assert captured["cmd"][idx + 1] == str(reports_dir.resolve())


def test_start_evaluation_always_passes_absolute_reports_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    captured = {}

    class StubJobs:
        def start_job(self, cmd, cwd, env):
            captured["cmd"] = cmd
            return {"jobId": "test"}

    provider = FilesystemActionProvider(job_manager=StubJobs())

    provider.start_evaluation(
        repo=str(repo_path),
        reports_dir="reports",
        options=EvaluationOptions(),
    )

    assert "-o" in captured["cmd"]
    idx = captured["cmd"].index("-o")
    assert Path(captured["cmd"][idx + 1]).is_absolute()


def test_start_evaluation_writes_repository_info(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    reports_dir = tmp_path / "reports"

    class StubJobs:
        def start_job(self, cmd, cwd, env):
            return {"jobId": "test"}

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
    assert payload["path"] == repo_path.resolve().name
    assert "uuid" in payload


def test_start_evaluation_writes_repository_info_for_online_repo(tmp_path: Path) -> None:
    repo_url = "git@github.com:example/acme-service.git"
    reports_dir = tmp_path / "reports"

    class StubJobs:
        def start_job(self, cmd, cwd, env):
            return {"jobId": "test"}

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
