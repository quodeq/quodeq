import pytest

from quodeq.data.web.http_client import HttpResponse
from quodeq.data.web.evaluations_repository import WebEvaluationsRepository
from quodeq.data.ports.data_errors import NotFoundError

_TEST_BASE_URL = "https://api.example.com"
_TEST_REPORTS_PATH = "/reports"
_TEST_RUN_ID = "run-1"


class FakeClient:
    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if url.endswith(_TEST_REPORTS_PATH):
            return HttpResponse(200, {"reports": [_TEST_RUN_ID]})
        if url.endswith(f"{_TEST_REPORTS_PATH}/{_TEST_RUN_ID}"):
            return HttpResponse(200, {"id": _TEST_RUN_ID})
        return HttpResponse(404, {"error": "not found"})


def test_web_evaluations_repository_reads_report():
    repo = WebEvaluationsRepository(base_url=_TEST_BASE_URL, client=FakeClient())
    assert repo.list_reports() == [_TEST_RUN_ID]
    payload = repo.get_report(_TEST_RUN_ID)
    assert payload["id"] == _TEST_RUN_ID


def test_web_evaluations_repository_404_raises():
    repo = WebEvaluationsRepository(base_url=_TEST_BASE_URL, client=FakeClient())
    with pytest.raises(NotFoundError):
        repo.get_report("nonexistent")
