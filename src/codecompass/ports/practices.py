from typing import Protocol


class PracticesRepository(Protocol):
    def list_topics(self, discipline: str) -> list[str]:
        """Return the names of all practice topics available for *discipline*."""
        ...

    def get_practice(self, discipline: str, topic: str) -> dict:
        """Return the practice document for *topic* under *discipline*."""
        ...
