from codecompass.adapters.web.http_client import HttpResponse
from codecompass.adapters.web.practices_repository import WebPracticesRepository


class FakeClient:
    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if url.endswith("/practices/backend"):
            return HttpResponse(200, {"topics": ["solid"]})
        if url.endswith("/practices/backend/solid"):
            return HttpResponse(200, {"metadata": {"topic": "SOLID"}})
        return HttpResponse(404, {"error": "not found"})


def test_web_practices_repository_reads_practice():
    repo = WebPracticesRepository(base_url="https://api.example.com", client=FakeClient())
    assert repo.list_topics("backend") == ["solid"]
    payload = repo.get_practice("backend", "solid")
    assert payload["metadata"]["topic"] == "SOLID"
