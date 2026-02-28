from typing import Protocol


class EvaluationsRepository(Protocol):
    def list_reports(self) -> list[str]:
        ...

    def get_report(self, report_id: str) -> dict:
        ...
