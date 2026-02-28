from codecompass.adapters.web.http_client import HttpResponse
from codecompass.adapters.web.dimensions_repository import WebDimensionsRepository


class FakeClient:
    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if url.endswith("/dimensions"):
            return HttpResponse(200, {"dimensions": ["robustness"]})
        if url.endswith("/dimensions/robustness"):
            return HttpResponse(200, {"metadata": {"name": "robustness"}})
        return HttpResponse(404, {"error": "not found"})


def test_web_dimensions_repository_reads_dimension():
    repo = WebDimensionsRepository(base_url="https://api.example.com", client=FakeClient())
    assert repo.list_dimensions() == ["robustness"]
    payload = repo.get_dimension("robustness")
    assert payload["metadata"]["name"] == "robustness"
