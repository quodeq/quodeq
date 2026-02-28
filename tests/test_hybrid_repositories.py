from codecompass.adapters.hybrid.practices_repository import HybridPracticesRepository
from codecompass.ports.data_errors import NetworkError, AuthError


class WebOk:
    def list_topics(self, discipline: str) -> list[str]:
        return ["solid"]

    def get_practice(self, discipline: str, topic: str) -> dict:
        return {"metadata": {"topic": "SOLID"}}


class WebDown:
    def list_topics(self, discipline: str) -> list[str]:
        raise NetworkError("down")

    def get_practice(self, discipline: str, topic: str) -> dict:
        raise NetworkError("down")


class WebUnauthorized:
    def list_topics(self, discipline: str) -> list[str]:
        raise AuthError("unauthorized")

    def get_practice(self, discipline: str, topic: str) -> dict:
        raise AuthError("unauthorized")


class FsRepo:
    def list_topics(self, discipline: str) -> list[str]:
        return ["fallback"]

    def get_practice(self, discipline: str, topic: str) -> dict:
        return {"metadata": {"topic": "FALLBACK"}}


def test_hybrid_practices_falls_back_on_network():
    repo = HybridPracticesRepository(web=WebDown(), fs=FsRepo())
    assert repo.list_topics("backend") == ["fallback"]


def test_hybrid_practices_no_fallback_on_auth():
    repo = HybridPracticesRepository(web=WebUnauthorized(), fs=FsRepo())
    try:
        repo.list_topics("backend")
    except AuthError:
        assert True
    else:
        assert False
