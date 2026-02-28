import pytest

from codecompass.evaluate.lib.dimensions import resolve_dimension_selection, list_available_dimensions


class FakeEvaluatorsRepo:
    def __init__(self, evaluators: list[str]) -> None:
        self._evaluators = evaluators

    def list_evaluators(self, discipline: str) -> list[str]:
        return list(self._evaluators)


def test_invalid_selection():
    with pytest.raises(ValueError):
        resolve_dimension_selection(["invalid"], ["valid"])


def test_list_available_dimensions_from_json():
    repo = FakeEvaluatorsRepo(["maintainability", "performance"])

    result = list_available_dimensions(repo, "backend")
    assert result == ["maintainability", "performance"]
