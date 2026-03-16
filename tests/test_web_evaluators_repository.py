from quodeq.adapters.web.http_client import HttpResponse
from quodeq.adapters.web.evaluators_repository import WebEvaluatorsRepository


class FakeClient:
    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if url.endswith("/evaluators/backend"):
            return HttpResponse(200, {"dimensions": ["robustness"]})
        if url.endswith("/evaluators/backend/robustness"):
            return HttpResponse(200, {"metadata": {"dimension": "robustness"}})
        return HttpResponse(404, {"error": "not found"})


def _make_repo() -> WebEvaluatorsRepository:
    return WebEvaluatorsRepository(base_url="https://api.example.com", client=FakeClient())


def test_list_evaluators_returns_dimensions():
    repo = _make_repo()
    assert repo.list_evaluators("backend") == ["robustness"]


def test_get_evaluator_returns_payload():
    repo = _make_repo()
    payload = repo.get_evaluator("backend", "robustness")
    assert payload["metadata"]["dimension"] == "robustness"
