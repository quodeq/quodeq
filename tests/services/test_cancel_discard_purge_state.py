"""Cancel with discard must leave nothing behind — cache/dir/index state.

Split from test_cancel_discard_purge.py.

New contract: discard == the run never happened.
- V2 cache entries written by ANY of the run's dims are wiped (done or not).
- The run directory and its index row are removed by the provider.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from quodeq.analysis.cache import CacheEntry, LocalFileBackend
from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state
from quodeq.data.fs.run_status_store import RunState, write_status
from quodeq.services._external_jobs import ProcessControl
from quodeq.services.evaluation_mixin import _discard_run_state
from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.services.jobs import JobManager


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


class TestDiscardRunState:
    def test_wipes_cache_for_all_dims_including_done(
        self, tmp_path: Path,
    ):
        """Every dim with a dispatch-keys sidecar gets its cache entries wiped.

        The sidecar holds exactly the keys of files THIS run analyzed
        (cache misses that were dispatched). Wiping them for done dims too is
        what makes the next incremental run stop counting the discarded run's
        files as "analyzed in previous runs".
        """
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

        _discard_run_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        }, cache=cache)

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
        self, tmp_path: Path,
    ):
        """A dim whose INCOMPLETE marker never landed (hard kill) is wiped.

        The old code keyed the cache wipe on dimensions.json state ==
        incomplete; a race with the subprocess's interrupt handler left the
        dim looking RUNNING and its cache entries alive.
        """
        reports, run = _seed_run(tmp_path)
        (run / "evidence" / "d1_dispatch_keys.json").write_text(
            json.dumps({"a.py": "kkkkk9"}),
        )
        (run / "evidence" / "d1_queue.json").write_text("{}")
        (run / "evidence" / "d1_fingerprint.json").write_text("{}")

        cache_root = tmp_path / "cache"
        cache = _seed_cache_entries(cache_root, ["kkkkk9"])

        # No dimensions.json at all. Must not crash, must still wipe.
        _discard_run_state(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        }, cache=cache)

        assert cache.get("kkkkk9") is None
        assert not (run / "evidence" / "d1_queue.json").exists()
        assert not (run / "evidence" / "d1_fingerprint.json").exists()

    def test_missing_sidecar_continues(self, tmp_path: Path):
        """A crash before the sidecar is written must not block discard."""
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

        # Intercept the tree-kill (we must not SIGTERM ourselves) and make
        # the liveness check report the pid dead once "killed" — but leave
        # status.json untouched, exactly like a wedged process would. Inject
        # via ProcessControl instead of patching module attributes.
        pid_killed = False

        def fake_kill_tree(target_pid: int, sig: int = _signal.SIGTERM) -> None:
            nonlocal pid_killed
            if sig == _signal.SIGTERM:
                pid_killed = True

        def fake_alive(query_pid: int) -> bool:
            return not pid_killed

        jm = JobManager(
            process_control=ProcessControl(kill_tree=fake_kill_tree, pid_alive=fake_alive),
        )
        provider = FilesystemActionProvider(job_manager=jm, index_db_path=db_path)
        provider.list_evaluations(limit=0, reports_dir=str(reports))

        ok = provider.cancel_evaluation(
            "ext-wedged-run", reports_dir=str(reports), discard_partial=True,
        )

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


def test_discard_removes_the_replayed_keys_sidecar(tmp_path: Path):
    """Every per-dim scratch file must go, or the status-GET scoring path can
    resurrect state from leftovers."""
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    sidecar = evidence / "security_replayed_unconsolidated_keys.json"
    sidecar.write_text(json.dumps({"a.py": "key-a"}))

    _discard_run_state(str(reports), {"outputProject": "proj", "outputRunId": "run1"})

    assert not sidecar.exists()


def test_discard_does_not_delete_replayed_cache_entries(tmp_path: Path):
    """The replayed entries were written by an EARLIER run. Discard wipes only
    what this run created; deleting these would destroy a prior kept run's
    cached work."""
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"b.py": "key-mine"})
    )
    (evidence / "security_replayed_unconsolidated_keys.json").write_text(
        json.dumps({"a.py": "key-theirs"})
    )

    deleted: list[str] = []

    class _FakeCache:
        def delete(self, key: str) -> None:
            deleted.append(key)

    _discard_run_state(
        str(reports), {"outputProject": "proj", "outputRunId": "run1"}, cache=_FakeCache(),
    )

    assert deleted == ["key-mine"]
