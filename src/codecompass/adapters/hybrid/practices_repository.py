from codecompass.ports.data_errors import InvalidDataError, NetworkError, ServerError
from codecompass.ports.practices import PracticesRepository


class HybridPracticesRepository:
    def __init__(self, web: PracticesRepository, fs: PracticesRepository) -> None:
        self._web = web
        self._fs = fs

    def list_topics(self, discipline: str) -> list[str]:
        try:
            return self._web.list_topics(discipline)
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.list_topics(discipline)

    def get_practice(self, discipline: str, topic: str) -> dict:
        try:
            return self._web.get_practice(discipline, topic)
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.get_practice(discipline, topic)
