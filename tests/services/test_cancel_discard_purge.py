"""Cancel with discard must leave nothing behind.

v1.6.0 bug: cancelling a run with "Discard findings" still produced a graded
run on the Overview. The cancel path scored completed dimensions BEFORE
discarding, the discard only wiped incomplete dims' scratch state, and the
run directory + index row survived. The accumulated view's cancelled-run
fallback then surfaced the grade the user asked to throw away.

New contract: discard == the run never happened.
- No scoring of completed evidence on the discard path.
- V2 cache entries written by ANY of the run's dims are wiped (done or not).
- The run directory and its index row are removed by the provider.
- The status-GET background-scoring path cannot resurrect the run.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.cache import CacheEntry, LocalFileBackend
from quodeq.core.types import JobSnapshot
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.shared.dimensions_state import DimState, write_dim_state
from quodeq.shared.run_status import RunState, write_status


def _seed_cache_entries(cache_root: Path, keys: list[str]) -> LocalFileBackend:
    cache = LocalFileBackend(root=cache_root)
    for k in keys:
        cache.put(k, CacheEntry(
            key=k, schema_version=2, findings=[],
            files_read=1, file_path=f"{k}.py", dimension="d", model_id="m",
        ))
    return cache


def _seed_run(tmp_path: Path) -> tuple[Path, Path]:
    reports = tmp_path / "reports"
    run = reports / "proj" / "run-1"
    (run / "evidence").mkdir(parents=True)
    (run / "evaluation").mkdir(parents=True)
    return reports, run


class TestDiscardSkipsScoring:
    def test_discard_does_not_score_completed_evidence(self):
        """With discard_partial=True, cancel must NOT write eval reports.

        Scoring first and discarding second is how the discarded run kept a
        grade: _score_completed_evidence wrote evaluation/<dim>.json for every
        finished dim, and the discard helper then explicitly preserved them.
        """
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._discard_run_state") as mock_discard, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"):
            result = m.cancel_evaluation(
                "j1", reports_dir="/reports", discard_partial=True,
            )
        assert result is True
        mock_score.assert_not_called()
        mock_discard.assert_called_once()

    def test_keep_findings_still_scores(self):
        """Without discard, the cancel path keeps scoring completed dims."""
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"):
            result = m.cancel_evaluation("j1", reports_dir="/reports")
        assert result is True
        mock_score.assert_called_once()


class TestDiscardRunState:
    def test_wipes_cache_for_all_dims_including_done(
        self, tmp_path: Path, monkeypatch,
    ):
        """Every dim with a dispatch-keys sidecar gets its cache entries wiped.

        The sidecar holds exactly the keys of files THIS run analyzed
        (cache misses that were dispatched). Wiping them for done dims too is
        what makes the next incremental run stop counting the discarded run's
        files as "analyzed in previous runs".
        """
        from quodeq.services.evaluation_mixin import _discard_run_state

        reports, run = _seed_run(tmp_path)

        (run / "evidence" / "d_inc_dispatch_keys.json").write_text(
            json.dumps({"a.py": "kkkkk1", "b.py": "kkkkk2"}),
        )
        (run / "evidence" / "d_inc_evidence.jsonl").write_text('{"file":"a.py"}\n')
        (run / "evidence" / "d_inc_queue.json").write_text("{}")
        (run / "evidence" / "d_done_dispatch_keys.json").write_text(
            json.dumps({"c.py": "kkkkk3"}),
        )
        (run / "evidence" / "d_done_evidence.jsonl").write_text('{"file":"c.py"}\n')
        (run / "evidence" / "d_done_queue.json").write_text("{}")
        (run / "evaluation" / "d_done.json").write_text("{}")

        write_dim_state(run, "d_inc", DimState.PENDING)
        write_dim_state(run, "d_inc", DimState.RUNNING)
        write_dim_state(run, "d_inc", DimState.INCOMPLETE, reason="cancelled_by_user")
        write_dim_state(run, "d_done", DimState.PENDING)
        write_dim_state(run, "d_done", DimState.RUNNING)
        write_dim_state(run, "d_done", DimState.DONE)

        cache_root = tmp_path / "cache"
        cache = _seed_cache_entries(cache_root, ["kkkkk1", "kkkkk2", "kkkkk3"])
        monkeypatch.setattr(
            "quodeq.services.evaluation_mixin._open_cache",
            lambda: cache,
        )

        _discard_run_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        assert cache.get("kkkkk1") is None
        assert cache.get("kkkkk2") is None
        assert cache.get("kkkkk3") is None, (
            "done dim's cache entries must be wiped too: discard means the "
            "run never happened"
        )
        assert not (run / "evidence" / "d_inc_evidence.jsonl").exists()
        assert not (run / "evidence" / "d_done_evidence.jsonl").exists(), (
            "scored dims' evidence must go too, or the status-GET scoring "
            "path resurrects the run from it"
        )

    def test_wipes_cache_even_without_dim_state(
        self, tmp_path: Path, monkeypatch,
    ):
        """A dim whose INCOMPLETE marker never landed (hard kill) is wiped.

        The old code keyed the cache wipe on dimensions.json state ==
        incomplete; a race with the subprocess's interrupt handler left the
        dim looking RUNNING and its cache entries alive.
        """
        from quodeq.services.evaluation_mixin import _discard_run_state

        reports, run = _seed_run(tmp_path)
        (run / "evidence" / "d1_dispatch_keys.json").write_text(
            json.dumps({"a.py": "kkkkk9"}),
        )
        (run / "evidence" / "d1_queue.json").write_text("{}")
        (run / "evidence" / "d1_fingerprint.json").write_text("{}")

        cache_root = tmp_path / "cache"
        cache = _seed_cache_entries(cache_root, ["kkkkk9"])
        monkeypatch.setattr(
            "quodeq.services.evaluation_mixin._open_cache",
            lambda: cache,
        )

        # No dimensions.json at all. Must not crash, must still wipe.
        _discard_run_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        assert cache.get("kkkkk9") is None
        assert not (run / "evidence" / "d1_queue.json").exists()
        assert not (run / "evidence" / "d1_fingerprint.json").exists()

    def test_missing_sidecar_continues(self, tmp_path: Path):
        """A crash before the sidecar is written must not block discard."""
        from quodeq.services.evaluation_mixin import _discard_run_state

        reports, run = _seed_run(tmp_path)
        (run / "evidence" / "d_inc_evidence.jsonl").write_text('{"file":"a.py"}\n')

        _discard_run_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        assert not (run / "evidence" / "d_inc_evidence.jsonl").exists()


class TestProviderDiscardPurgesRun:
    def test_discard_removes_run_dir_and_index_row(self, tmp_path: Path) -> None:
        """Provider-level discard: nothing of the run survives.

        Uses the orphaned-external-run path (dead PID) so no real subprocess
        is needed; the same purge must run after any successful cancel.
        """
        reports = tmp_path / "reports"
        run = reports / "p" / "stale-run"
        (run / "evidence").mkdir(parents=True)
        (run / "evidence" / "manifest.json").write_text("{}")
        write_status(
            run, state=RunState.RUNNING, job_id="ext-stale-run",
            started_at="2026-04-20T00:00:00+00:00", dimensions=["security"],
            pid=999999999,
        )
        (run / ".heartbeat").touch()
        (run / ".pid").write_text("999999999")
        (run / "evidence" / "security_evidence.jsonl").write_text('{"finding":"x"}\n')

        db_path = tmp_path / "idx.db"
        provider = FilesystemActionProvider(index_db_path=db_path)
        provider.list_evaluations(limit=0, reports_dir=str(reports))

        ok = provider.cancel_evaluation(
            "ext-stale-run", reports_dir=str(reports), discard_partial=True,
        )
        assert ok is True

        assert not run.exists(), "discard must remove the run directory"
        snapshot = provider.get_evaluation_status(
            "ext-stale-run", reports_dir=str(reports),
        )
        assert snapshot is None, "discarded run must be gone from the index"
        listed = provider.list_evaluations(limit=0, reports_dir=str(reports))
        assert all(s.job_id != "ext-stale-run" for s in listed)

    def test_discard_purges_even_when_status_never_flips_terminal(
        self, tmp_path: Path,
    ) -> None:
        """A killed process that never writes a terminal status.json must not
        block the purge.

        Real-world shape of the bug report: the user cancels a wedged run.
        The SIGTERM lands (cancel returns True) but the dying process never
        flips status.json to cancelled, so the index still reads "running"
        and EvaluationsIndex.delete refuses the row. The discard must
        promote the stale row and purge anyway.
        """
        import signal as _signal

        reports = tmp_path / "reports"
        run = reports / "p" / "wedged-run"
        (run / "evidence").mkdir(parents=True)
        (run / "evidence" / "manifest.json").write_text("{}")
        write_status(
            run, state=RunState.RUNNING, job_id="ext-wedged-run",
            started_at="2026-04-20T00:00:00+00:00", dimensions=["security"],
            pid=os.getpid(),
        )
        (run / ".heartbeat").touch()
        (run / ".pid").write_text(str(os.getpid()))

        db_path = tmp_path / "idx.db"
        provider = FilesystemActionProvider(index_db_path=db_path)
        provider.list_evaluations(limit=0, reports_dir=str(reports))

        # Intercept the tree-kill (we must not SIGTERM ourselves) and make
        # the liveness check report the pid dead once "killed" — but leave
        # status.json untouched, exactly like a wedged process would.
        import quodeq.services._external_jobs as _ext_mod
        import quodeq.services._index_sync as _sync_mod
        original_kill_tree = _ext_mod._kill_tree
        original_alive = _sync_mod._is_pid_alive
        pid_killed = False

        def fake_kill_tree(target_pid: int, sig: int = _signal.SIGTERM) -> None:
            nonlocal pid_killed
            if sig == _signal.SIGTERM:
                pid_killed = True

        def fake_alive(query_pid: int) -> bool:
            if pid_killed:
                return False
            return original_alive(query_pid)

        _ext_mod._kill_tree = fake_kill_tree
        _sync_mod._is_pid_alive = fake_alive
        try:
            ok = provider.cancel_evaluation(
                "ext-wedged-run", reports_dir=str(reports), discard_partial=True,
            )
        finally:
            _ext_mod._kill_tree = original_kill_tree
            _sync_mod._is_pid_alive = original_alive

        assert ok is True
        assert not run.exists(), (
            "discard must purge the run even when the killed process never "
            "wrote a terminal status.json"
        )
        listed = provider.list_evaluations(limit=0, reports_dir=str(reports))
        assert all(s.job_id != "ext-wedged-run" for s in listed)

    def test_keep_findings_preserves_run_dir(self, tmp_path: Path) -> None:
        """Without discard, cancel keeps the run on disk (existing contract)."""
        reports = tmp_path / "reports"
        run = reports / "p" / "keep-run"
        (run / "evidence").mkdir(parents=True)
        (run / "evidence" / "manifest.json").write_text("{}")
        write_status(
            run, state=RunState.RUNNING, job_id="ext-keep-run",
            started_at="2026-04-20T00:00:00+00:00", dimensions=["security"],
            pid=999999999,
        )
        (run / ".heartbeat").touch()
        (run / ".pid").write_text("999999999")

        db_path = tmp_path / "idx.db"
        provider = FilesystemActionProvider(index_db_path=db_path)
        provider.list_evaluations(limit=0, reports_dir=str(reports))

        ok = provider.cancel_evaluation(
            "ext-keep-run", reports_dir=str(reports), discard_partial=False,
        )
        assert ok is True
        assert run.exists(), "keep-findings cancel must preserve the run dir"


class TestRouteDiscardBlocksScoringResurrection:
    """DELETE ?discard=true must pre-claim the scoring registry.

    Without the claim, the very next status GET (the UI polls every 1.5s)
    sees status == cancelled and spawns _score_completed_evidence in the
    background, re-writing eval reports for whatever evidence survives the
    purge race.
    """

    def _make_app(self):
        from quodeq.api.app import create_app

        class _Provider(FilesystemActionProvider):
            pass

        provider = MagicMock()
        provider.get_evaluation_status.return_value = JobSnapshot(
            job_id="j-disc", status="running",
            output_project="proj", output_run_id="run-d",
        )
        provider.cancel_evaluation.return_value = True
        app = create_app(provider)
        return app, provider

    @pytest.fixture(autouse=True)
    def _reset_claim_registry(self, monkeypatch):
        from quodeq.api._evaluation_routes import _scored_jobs, _scored_jobs_lock
        monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
        with _scored_jobs_lock:
            _scored_jobs.clear()
        yield
        with _scored_jobs_lock:
            _scored_jobs.clear()

    def test_get_after_discard_cancel_does_not_score(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
        app, provider = self._make_app()
        client = app.test_client()

        resp = client.delete(
            "/api/evaluations/j-disc?discard=true",
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["discarded"] is True

        # Job is now terminal; the UI's next poll arrives.
        provider.get_evaluation_status.return_value = JobSnapshot(
            job_id="j-disc", status="cancelled",
            output_project="proj", output_run_id="run-d",
        )
        scored = threading.Event()
        with patch(
            "quodeq.api._evaluation_routes._score_completed_evidence",
            side_effect=lambda *a, **k: scored.set(),
        ):
            get_resp = client.get("/api/evaluations/j-disc")
            assert get_resp.status_code == 200
            # Give a would-be background thread time to start.
            assert not scored.wait(timeout=0.3), (
                "status GET resurrected scoring for a discarded run"
            )
