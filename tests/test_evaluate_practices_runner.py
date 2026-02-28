from pathlib import Path

import pytest

from codecompass.evaluate.lib.practices_runner import (
    build_practices_prompt,
    build_practices_evaluation,
    resolve_selected_practice_names,
    run_practices,
)


class FakePracticesRepo:
    def __init__(self, topics: list[str], practices: dict[str, dict]) -> None:
        self._topics = topics
        self._practices = practices

    def list_topics(self, discipline: str) -> list[str]:
        return list(self._topics)

    def get_practice(self, discipline: str, topic: str) -> dict:
        return self._practices.get(topic, {"body": "", "metadata": {}})


def test_resolve_selected_practice_names_all():
    assert resolve_selected_practice_names(["a", "b"], []) == ["a", "b"]


def test_resolve_selected_practice_names_indices():
    assert resolve_selected_practice_names(["a", "b"], [2]) == ["b"]
    with pytest.raises(ValueError):
        resolve_selected_practice_names(["a"], [2])


def test_build_practices_prompt_replaces_fields():
    template = "D={{DISCIPLINE}} L={{PRACTICES_LIST}} R={{REPO_NAME}} T={{DATE}} O={{OUTPUT_PATH}}"
    prompt = build_practices_prompt(
        template=template,
        discipline="frontend",
        project_name="demo",
        today="2026-02-25",
        output_file="/tmp/out.md",
        practices_list="a, b",
        practices_content="CONTENT",
    )

    assert "D=frontend" in prompt
    assert "L=a, b" in prompt
    assert "R=demo" in prompt
    assert "T=2026-02-25" in prompt
    assert "O=/tmp/out.md" in prompt
    assert "Practice Documents to Evaluate" in prompt
    assert "CONTENT" in prompt


def test_build_practices_evaluation_builds_content():
    repo = FakePracticesRepo(
        topics=["alpha", "beta"],
        practices={
            "alpha": {"body": "Alpha body"},
            "beta": {"body": "Beta body"},
        },
    )

    template = "{{PRACTICES_LIST}}"
    result = build_practices_evaluation(
        discipline="frontend_react",
        practices_repo=repo,
        selected_indices=[],
        template=template,
        project_name="demo",
        today="2026-02-25",
        output_file="/tmp/out.md",
    )

    assert result["practices_list"] == "alpha, beta"
    assert "Alpha body" in result["practices_content"]
    assert "Beta body" in result["practices_content"]
    assert result["output_file"] == "/tmp/out.md"


def test_build_practices_evaluation_missing_dir():
    repo = FakePracticesRepo(topics=[], practices={})
    with pytest.raises(FileNotFoundError):
        build_practices_evaluation(
            discipline="missing",
            practices_repo=repo,
            selected_indices=[],
            template="x",
            project_name="demo",
            today="2026-02-25",
            output_file="/tmp/out.md",
        )


def test_run_practices_writes_output(tmp_path: Path):
    repo = FakePracticesRepo(
        topics=["alpha"],
        practices={"alpha": {"body": "Alpha body"}},
    )

    template = "T={{DATE}}"
    output_file = tmp_path / "out.md"

    result = run_practices(
        discipline="frontend_react",
        practices_repo=repo,
        template=template,
        project_name="demo",
        today="2026-02-25",
        output_file=output_file,
        selected_indices=[],
    )

    assert output_file.read_text() == result["prompt"]
    assert result["output_file"] == str(output_file)
