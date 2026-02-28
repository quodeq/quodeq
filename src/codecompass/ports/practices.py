from typing import Protocol


class PracticesRepository(Protocol):
    def list_topics(self, discipline: str) -> list[str]:
        ...

    def get_practice(self, discipline: str, topic: str) -> dict:
        ...
