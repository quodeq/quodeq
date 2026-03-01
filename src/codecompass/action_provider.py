from __future__ import annotations


class ActionProvider:
    def list_projects(self, reports_dir: str):
        raise NotImplementedError

    def get_dashboard(self, reports_dir: str, project: str, run: str):
        raise NotImplementedError

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None):
        raise NotImplementedError

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str):
        raise NotImplementedError

    def get_run_plan(self, reports_dir: str, project: str, run_id: str):
        raise NotImplementedError

    def get_violations(self, reports_dir: str, project: str, run_id: str):
        raise NotImplementedError

    def start_evaluation(self, repo: str, discipline: str | None, dimensions: str, numerical: bool, reports_dir: str):
        raise NotImplementedError

    def get_evaluation_status(self, job_id: str):
        raise NotImplementedError

    def cancel_evaluation(self, job_id: str) -> bool:
        raise NotImplementedError

    def browse_repo(self, path: str | None):
        raise NotImplementedError
