from typing import Protocol


class DimensionsRepository(Protocol):
    def list_dimensions(self) -> list[str]:
        ...

    def get_dimension(self, name: str) -> dict:
        ...
