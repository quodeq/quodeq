"""DI seams for mutation_rescore: injectable project locks and repo factory."""
from __future__ import annotations


def test_project_lock_registry_shares_per_project_and_clears():
    from quodeq.services.mutation_rescore import ProjectLockRegistry

    reg = ProjectLockRegistry()
    a = reg.get("proj-a")
    assert reg.get("proj-a") is a
    assert reg.get("proj-b") is not a
    reg.clear()
    assert reg.get("proj-a") is not a


def test_project_all_runs_uses_injected_repo_factory(tmp_path):
    from quodeq.services.mutation_rescore import _project_all_runs

    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "events.jsonl").write_text("")
    (tmp_path / "r2").mkdir()  # no events.jsonl -> skipped

    seen = []

    class _FakeRepo:
        def __init__(self, run_dir):
            self._run_dir = run_dir

        def ensure_projected(self):
            seen.append(self._run_dir)

    _project_all_runs(tmp_path, repo_factory=_FakeRepo)

    assert seen == [tmp_path / "r1"]
    assert not (tmp_path / "r1" / "evaluation.db").exists()
