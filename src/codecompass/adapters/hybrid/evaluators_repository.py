from codecompass.ports.data_errors import InvalidDataError, NetworkError, ServerError


class HybridEvaluatorsRepository:
    def __init__(self, web, fs) -> None:
        self._web = web
        self._fs = fs

    def list_evaluators(self, discipline: str) -> list[str]:
        try:
            return self._web.list_evaluators(discipline)
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.list_evaluators(discipline)

    def get_evaluator(self, discipline: str, dimension: str) -> dict:
        try:
            return self._web.get_evaluator(discipline, dimension)
        except (NetworkError, ServerError, InvalidDataError):
            return self._fs.get_evaluator(discipline, dimension)
