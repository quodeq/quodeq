import json
from pathlib import Path

from codecompass.bootstrap import DataProvider
from codecompass.evaluate.runner import run_practices_mode


class FakePracticesRepo:
    def __init__(self, practices: dict[str, dict]) -> None:
        self._practices = practices

    def list_topics(self, discipline: str) -> list[str]:
        return list(self._practices.keys())

    def get_practice(self, discipline: str, topic: str) -> dict:
        return self._practices.get(topic, {"body": "", "metadata": {}})


def test_run_practices_mode_writes_output(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    template_path = tmp_path / "practices-evaluator.md"
    template_path.write_text("DATE={{DATE}}")

    output_file = tmp_path / "practices_eval.md"

    repo = FakePracticesRepo({"alpha": {"body": "Alpha body"}})
    provider = DataProvider(practices=repo)

    captured = {}

    def fake_ai_cli(prompt: str):
        captured["prompt"] = prompt
        return "AI OUTPUT", None

    monkeypatch.setattr("codecompass.evaluate.runner.run_ai_cli", fake_ai_cli)

    result = run_practices_mode(
        repo_path=str(repo_dir),
        discipline="frontend_react",
        provider=provider,
        template_path=template_path,
        output_file=output_file,
        selected_indices=[],
        today="2026-02-25",
    )

    assert result == 0
    assert output_file.read_text() == "AI OUTPUT"
    assert "Alpha body" in captured["prompt"]


def test_run_practices_mode_writes_ai_output(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    template_path = tmp_path / "practices-evaluator.md"
    template_path.write_text("DATE={{DATE}}")

    output_file = tmp_path / "practices_eval.md"

    repo = FakePracticesRepo({"alpha": {"body": "Alpha body"}})
    provider = DataProvider(practices=repo)

    def fake_ai_cli(prompt: str):
        return "AI OUTPUT", None

    monkeypatch.setattr("codecompass.evaluate.runner.run_ai_cli", fake_ai_cli)

    result = run_practices_mode(
        repo_path=str(repo_dir),
        discipline="frontend_react",
        provider=provider,
        template_path=template_path,
        output_file=output_file,
        selected_indices=[],
        today="2026-02-25",
    )

    assert result == 0
    assert output_file.read_text() == "AI OUTPUT"


def test_run_practices_mode_ai_error_returns_failure(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    template_path = tmp_path / "practices-evaluator.md"
    template_path.write_text("DATE={{DATE}}")

    output_file = tmp_path / "practices_eval.md"
    output_file.write_text("old")

    repo = FakePracticesRepo({"alpha": {"body": "Alpha body"}})
    provider = DataProvider(practices=repo)

    def fake_ai_cli(prompt: str):
        return None, "AI command not found: claude"

    monkeypatch.setattr("codecompass.evaluate.runner.run_ai_cli", fake_ai_cli)

    result = run_practices_mode(
        repo_path=str(repo_dir),
        discipline="frontend_react",
        provider=provider,
        template_path=template_path,
        output_file=output_file,
        selected_indices=[],
        today="2026-02-25",
    )

    assert result == 1
    assert output_file.read_text() == "old"


def test_run_practices_mode_no_prescan_skips_metrics(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    template_path = tmp_path / "practices-evaluator.md"
    template_path.write_text("DATE={{DATE}}")

    output_file = tmp_path / "practices_eval.md"

    repo = FakePracticesRepo({"alpha": {"body": "Alpha body"}})
    provider = DataProvider(practices=repo)

    def fake_ai_cli(prompt: str):
        return prompt, None

    def fake_prescan(work_dir: str, discipline: str):
        return "PRESCAN SUMMARY"

    monkeypatch.setattr("codecompass.evaluate.runner.run_ai_cli", fake_ai_cli)
    monkeypatch.setattr("codecompass.evaluate.runner.run_prescan_metrics", fake_prescan)

    result = run_practices_mode(
        repo_path=str(repo_dir),
        discipline="frontend_react",
        provider=provider,
        template_path=template_path,
        output_file=output_file,
        selected_indices=[],
        today="2026-02-25",
        no_prescan=True,
    )

    assert result == 0
    assert "PRESCAN SUMMARY" not in output_file.read_text()
