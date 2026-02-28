from codecompass.ports.data_errors import InvalidDataError, NetworkError, ServerError


class HybridDimensionsRepository:
    def __init__(self, web, fs) -> None:
        self._web = web
        self._fs = fs

    def list_dimensions(self) -> list[str]:
        try:
            return self._web.list_dimensions()
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.list_dimensions()

    def get_dimension(self, name: str) -> dict:
        try:
            return self._web.get_dimension(name)
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.get_dimension(name)
