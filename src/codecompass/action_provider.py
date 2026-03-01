from __future__ import annotations


class ActionProvider:
    def list_projects(self, reports_dir: str) -> dict:
        raise NotImplementedError

    def get_project_info(self, reports_dir: str, project: str) -> dict:
        raise NotImplementedError

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict:
        raise NotImplementedError

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict:
        raise NotImplementedError

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict:
        raise NotImplementedError

    def get_run_plan(self, reports_dir: str, project: str, run_id: str) -> dict:
        raise NotImplementedError

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> dict:
        raise NotImplementedError

    def start_evaluation(self, repo: str, discipline: str | None, dimensions: str, numerical: bool, reports_dir: str, ai_cmd: str | None = None, ai_model: str | None = None) -> dict:
        raise NotImplementedError

    def get_evaluation_status(self, job_id: str) -> dict:
        raise NotImplementedError

    def cancel_evaluation(self, job_id: str) -> bool:
        raise NotImplementedError

    def browse_repo(self, path: str | None) -> dict:
        raise NotImplementedError

    def get_ai_clients(self) -> dict:
        raise NotImplementedError

    def get_client_models(self, client_id: str) -> dict:
        raise NotImplementedError
