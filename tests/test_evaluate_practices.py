import pytest

from codecompass.evaluate.lib.practices import (
    list_practice_files,
    resolve_practice,
    extract_practice_metadata,
)


class FakePracticesRepo:
    def __init__(self, topics: list[str] | None = None, practices: dict | None = None) -> None:
        self._topics = topics or []
        self._practices = practices or {}

    def list_topics(self, discipline: str) -> list[str]:
        return list(self._topics)

    def get_practice(self, discipline: str, topic: str) -> dict:
        return self._practices.get(topic, {"body": "", "metadata": {}})


def test_list_practice_files_sorted():
    repo = FakePracticesRepo(topics=["a_practice", "b_practice"])

    result = list_practice_files(repo, "frontend")

    assert result == ["a_practice", "b_practice"]


def test_resolve_practice_index():
    repo = FakePracticesRepo(topics=["first", "second"])

    assert resolve_practice(2, repo, "frontend") == "second"


def test_resolve_practice_out_of_range():
    repo = FakePracticesRepo(topics=["only"])

    with pytest.raises(ValueError):
        resolve_practice(2, repo, "frontend")


def test_extract_practice_metadata_prefers_json():
    repo = FakePracticesRepo(
        topics=["topic_name"],
        practices={
            "topic_name": {
                "body": "body",
                "metadata": {"topic": "Custom Topic", "language": "python"},
            }
        },
    )

    topic, language = extract_practice_metadata(repo, "frontend_react", "topic_name")

    assert topic == "Custom Topic"
    assert language == "python"


def test_extract_practice_metadata_fallbacks():
    repo = FakePracticesRepo(
        topics=["clean_architecture"],
        practices={"clean_architecture": {"body": "body", "metadata": {}}},
    )

    topic, language = extract_practice_metadata(repo, "frontend_react", "clean_architecture")

    assert topic == "Clean Architecture"
    assert language == "text"
