import importlib

from quodeq.core.types.sync_phase import SyncPhase

_steps = importlib.import_module("quodeq.services._project_registration_steps")
MaterializeRequest, materialize_and_scan = _steps.MaterializeRequest, _steps.materialize_and_scan


def test_materialize_reports_reading_before_scan_for_a_local_folder(monkeypatch, tmp_path):
    phases, order = [], []
    monkeypatch.setattr("quodeq.services._project_registration_steps.scan_project", lambda *a, **k: order.append("scan"))
    monkeypatch.setattr("quodeq.services._project_registration_steps._persist_repository_info", lambda *a, **k: None)
    repo = tmp_path / "repo"
    repo.mkdir()
    project_dir = tmp_path / "p"
    project_dir.mkdir()
    req = MaterializeRequest(
        repo=str(repo), repo_resolved=str(repo), project_name="repo", project_uuid="u",
        project_dir=project_dir, reports_path=tmp_path, scope_path=None, is_url=False, ephemeral=False,
        clone_dest=None, clones_dir=None, on_phase=lambda p: (phases.append(p), order.append("phase")),
    )
    materialize_and_scan(req)
    assert phases == [SyncPhase.READING] and order == ["phase", "scan"]
