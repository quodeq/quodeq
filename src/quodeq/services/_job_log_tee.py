"""Stream-consumption and run.log tee logic for JobManager, split out of
jobs.py (Task 13) as free functions.

``JobManager._consume_stream``/``_tee_run_log``/``_drain_pre_marker_buffer``
become thin delegates that pass in the per-job state they exclusively own
(``_run_log_writers``, ``_pre_marker_buffer``) plus their store/reports_root/
log/flush_batch collaborators. The bodies below are moved verbatim from
those methods -- this is background-thread code (the per-job
``_consume_stream`` thread started in ``JobManager.start_job``), so lock
acquisitions and flush points are unchanged from the pre-split methods; see
``JobManager.__init__`` for the "no other code path may read or mutate
these dicts" invariant that still applies to the dicts passed in here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from quodeq.core.observability import LogSink
from quodeq.services._job_model import JobStore, _CC_MARKER_PREFIX, _CONSUME_BATCH_SIZE
from quodeq.shared.run_log import RunLogWriter


def _read_and_tee_loop(
    job_id: str,
    stream: Iterable[str],
    batch: list[str],
    *,
    store: JobStore,
    reports_root: Path | None,
    run_log_writers: dict[str, RunLogWriter],
    pre_marker_buffer: dict[str, list[str]],
    log: LogSink,
    flush_batch: Callable[[str, list[str]], bool],
) -> bool:
    """Read *stream* lines into *batch*, teeing each to run.log.

    Returns False if the job disappeared mid-stream (a flush found no job
    left in the store) -- the caller must then skip the post-loop flush and
    drain, though its ``finally`` still runs the writer/buffer cleanup.
    """
    try:
        for line in stream:
            stripped = line.rstrip("\n")
            batch.append(stripped)
            if len(batch) >= _CONSUME_BATCH_SIZE:
                if not flush_batch(job_id, batch):
                    return False
                batch.clear()
            # Tee after flush so the marker is already applied to the job
            # before we try to resolve run_dir. Skip _cc JSON markers —
            # they are structured IPC, not user-facing terminal output, and
            # leaking them makes the xterm pane in the dashboard noisy.
            if not stripped.startswith(_CC_MARKER_PREFIX):
                tee_run_log(
                    job_id, stripped, store=store, reports_root=reports_root,
                    run_log_writers=run_log_writers, pre_marker_buffer=pre_marker_buffer,
                )
    except (IOError, BrokenPipeError) as exc:
        log.warning(f"Stream read error for job {job_id}: {exc}")
    return True


def consume_stream(
    job_id: str,
    stream: Iterable[str] | None,
    *,
    store: JobStore,
    reports_root: Path | None,
    run_log_writers: dict[str, RunLogWriter],
    pre_marker_buffer: dict[str, list[str]],
    log: LogSink,
    flush_batch: Callable[[str, list[str]], bool],
) -> None:
    if stream is None:
        return
    batch: list[str] = []
    pre_marker_buffer.setdefault(job_id, [])
    try:
        if _read_and_tee_loop(
            job_id, stream, batch, store=store, reports_root=reports_root,
            run_log_writers=run_log_writers, pre_marker_buffer=pre_marker_buffer,
            log=log, flush_batch=flush_batch,
        ):
            if batch:
                flush_batch(job_id, batch)
            # Final drain: if the report_path marker arrived in the last
            # batch, the writer may not have been created yet — try one
            # more time so buffered pre-marker lines are not lost.
            drain_pre_marker_buffer(
                job_id, store=store, reports_root=reports_root,
                run_log_writers=run_log_writers, pre_marker_buffer=pre_marker_buffer,
            )
    finally:
        # Always release the writer and buffer, even on unexpected exceptions.
        writer = run_log_writers.pop(job_id, None)
        if writer is not None:
            writer.close()
        pre_marker_buffer.pop(job_id, None)


def drain_pre_marker_buffer(
    job_id: str,
    *,
    store: JobStore,
    reports_root: Path | None,
    run_log_writers: dict[str, RunLogWriter],
    pre_marker_buffer: dict[str, list[str]],
) -> None:
    """Attempt to resolve run_dir and flush any buffered pre-marker lines.

    Called after the final flush_batch so that lines buffered before the
    report_path marker are not lost when the marker arrives in the last
    batch of the stream.
    """
    if run_log_writers.get(job_id) is not None:
        # Writer already open — nothing to drain.
        return
    job = store.get(job_id)
    if job and job.output_project and job.output_run_id and reports_root is not None:
        run_dir = reports_root / job.output_project / job.output_run_id
        if run_dir.is_dir():
            writer = RunLogWriter(run_dir)
            run_log_writers[job_id] = writer
            for pending in pre_marker_buffer.get(job_id, []):
                writer.write(pending)
            pre_marker_buffer[job_id] = []


def tee_run_log(
    job_id: str,
    line: str,
    *,
    store: JobStore,
    reports_root: Path | None,
    run_log_writers: dict[str, RunLogWriter],
    pre_marker_buffer: dict[str, list[str]],
) -> None:
    """Forward *line* to the job's run.log writer.

    Before the report_path marker arrives, ``run_dir`` is unknown — lines
    are held in ``pre_marker_buffer`` and flushed once the marker resolves
    the directory.

    Caller invariant: at most one ``consume_stream`` runs per job_id at a
    time. This function is not re-entrant for the same job_id.
    """
    writer = run_log_writers.get(job_id)
    if writer is None:
        # Try to resolve run_dir from the job snapshot now.
        job = store.get(job_id)
        if job and job.output_project and job.output_run_id and reports_root is not None:
            run_dir = reports_root / job.output_project / job.output_run_id
            if run_dir.is_dir():
                writer = RunLogWriter(run_dir)
                run_log_writers[job_id] = writer
                # Flush any buffered pre-marker lines.
                for pending in pre_marker_buffer.get(job_id, []):
                    writer.write(pending)
                pre_marker_buffer[job_id] = []
        if writer is None:
            pre_marker_buffer.setdefault(job_id, []).append(line)
            return
    writer.write(line)
