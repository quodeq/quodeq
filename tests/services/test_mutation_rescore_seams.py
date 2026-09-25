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
    from quodeq.services.mutation_rescore import project_all_runs

    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "events.jsonl").write_text("")
    (tmp_path / "r2").mkdir()  # no events.jsonl -> skipped

    seen = []

    class _FakeRepo:
        def __init__(self, run_dir):
            self._run_dir = run_dir

        def ensure_projected(self):
            seen.append(self._run_dir)

    project_all_runs(tmp_path, repo_factory=_FakeRepo)

    assert seen == [tmp_path / "r1"]
    assert not (tmp_path / "r1" / "evaluation.db").exists()


def test_project_all_runs_uses_the_injected_log_over_the_default(tmp_path):
    """#10795 — ``log=`` is a real injection seam, not just a sentinel."""
    from quodeq.services.mutation_rescore import project_all_runs

    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "events.jsonl").write_text("")

    class _BoomRepo:
        def __init__(self, run_dir):
            self._run_dir = run_dir

        def ensure_projected(self):
            raise RuntimeError("boom")

    warnings = []

    class _FakeLog:
        def warning(self, msg):
            warnings.append(msg)

    project_all_runs(tmp_path, repo_factory=_BoomRepo, log=_FakeLog())

    assert len(warnings) == 1
    assert "boom" in warnings[0]


def test_project_all_runs_explicit_log_none_falls_back_like_omitting_it(tmp_path, caplog):
    """#10795 — the call-time default is ``log: LogSink | None = None``, not
    ``log: LogSink = NULL_LOG``: passing ``log=None`` explicitly (what a
    caller resolving its own optional collaborator would do) must fall back
    the same way omitting the kwarg does, not crash trying to call
    ``None.warning(...)``."""
    import logging
    from quodeq.services.mutation_rescore import project_all_runs

    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "events.jsonl").write_text("")

    class _BoomRepo:
        def __init__(self, run_dir):
            self._run_dir = run_dir

        def ensure_projected(self):
            raise RuntimeError("boom-explicit-none")

    with caplog.at_level(logging.WARNING, logger="quodeq.services.mutation_rescore"):
        project_all_runs(tmp_path, repo_factory=_BoomRepo, log=None)

    matching = [r for r in caplog.records if "boom-explicit-none" in r.message]
    assert matching, [(r.name, r.message) for r in caplog.records]
    assert matching[0].name == "quodeq.services.mutation_rescore"


def test_project_all_runs_falls_back_to_the_mutation_rescore_logger_by_name(tmp_path, caplog):
    """#10795 — with no ``log=`` injected, the failure is still observable,
    logged under ``quodeq.services.mutation_rescore`` (caplog tests capture
    that name, not ``_mutation_projection``)."""
    import logging
    from quodeq.services.mutation_rescore import project_all_runs

    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "events.jsonl").write_text("")

    class _BoomRepo:
        def __init__(self, run_dir):
            self._run_dir = run_dir

        def ensure_projected(self):
            raise RuntimeError("boom-default")

    with caplog.at_level(logging.WARNING, logger="quodeq.services.mutation_rescore"):
        project_all_runs(tmp_path, repo_factory=_BoomRepo)

    matching = [r for r in caplog.records if "boom-default" in r.message]
    assert matching, [(r.name, r.message) for r in caplog.records]
    assert matching[0].name == "quodeq.services.mutation_rescore"
