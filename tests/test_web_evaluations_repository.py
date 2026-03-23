import pytest

from quodeq.adapters.web.http_client import HttpResponse
from quodeq.adapters.web.evaluations_repository import WebEvaluationsRepository
from quodeq.data.ports.data_errors import NotFoundError


class FakeClient:
    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if url.endswith("/reports"):
            return HttpResponse(200, {"reports": ["run-1"]})
        if url.endswith("/reports/run-1"):
            return HttpResponse(200, {"id": "run-1"})
        return HttpResponse(404, {"error": "not found"})


def test_web_evaluations_repository_reads_report():
    repo = WebEvaluationsRepository(base_url="https://api.example.com", client=FakeClient())
    assert repo.list_reports() == ["run-1"]
    payload = repo.get_report("run-1")
    assert payload["id"] == "run-1"


def test_web_evaluations_repository_404_raises():
    repo = WebEvaluationsRepository(base_url="https://api.example.com", client=FakeClient())
    with pytest.raises(NotFoundError):
        repo.get_report("nonexistent")
