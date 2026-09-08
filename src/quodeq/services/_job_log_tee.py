"""Stream-consumption and run.log tee logic for JobManager, split out of
jobs.py (Task 13) as free functions.

``JobManager._consume_stream``/``_tee_run_log``/``_drain_pre_marker_buffer``
become thin delegates that pass in the per-job state they exclusively own
(``_run_log_writers``, ``_pre_marker_buffer``) plus their store/reports_root/
log/flush_batch collaborators. This is background-thread code (the per-job
``_consume_stream`` thread started in ``JobManager.start_job``); see
``JobManager.__init__`` for the "no other code path may read or mutate
these dicts" invariant that still applies to the dicts passed in here.

Lines reach the job one ``flush_batch`` per pipe read (``_iter_line_batches``)
rather than per fixed line count: a count of 50 made the live terminal lag
(reverted in 41a0012f), a count of 1 paid the job lock once per line. A
read boundary keeps the latency of the latter with the amortization of the
former, because nothing is held back while waiting for more output.
"""
from __future__ import annotations

import codecs
import io
from pathlib import Path
from typing import Callable, Iterable, Iterator

from quodeq.core.observability import LogSink
from quodeq.services._job_model import JobStore, _CC_MARKER_PREFIX
from quodeq.shared.run_log import RunLogWriter


def _iter_line_batches(stream: Iterable[str]) -> Iterator[list[str]]:
    """Yield the newline-stripped lines each read of *stream* returned.

    Iterating a text pipe line by line hides how much the child wrote at
    once: a burst lands in the TextIOWrapper's buffer and comes back one
    line per ``__next__``. Reading the underlying byte buffer with ``read1``
    (one raw read, whatever is available) exposes that burst as the batch
    without waiting for more. Decoding mirrors the wrapper's own encoding,
    errors and universal-newline translation. Streams without a byte buffer
    (test iterables, StringIO) yield one line per batch.
    """
    read1 = getattr(getattr(stream, "buffer", None), "read1", None)
    encoding = getattr(stream, "encoding", None)
    if read1 is None or not isinstance(encoding, str):
        for line in stream:
            yield [line.rstrip("\n")]
        return
    decoder = io.IncrementalNewlineDecoder(
        codecs.getincrementaldecoder(encoding)(getattr(stream, "errors", None) or "strict"),
        translate=True,
    )
    parts: list[str] = []  # pieces of the line the reads so far left open
    while True:
        chunk = read1(io.DEFAULT_BUFFER_SIZE)
        text = decoder.decode(chunk, final=not chunk)
        parts.append(text)
        if chunk and "\n" not in text:
            # Still inside one line: join only once a newline (or EOF) lands,
            # so a long line costs one copy rather than one per read.
            continue
        lines = "".join(parts).split("\n")
        tail = lines.pop()
        parts = [tail] if tail else []
        if not chunk and tail:
            lines.append(tail)
        if lines:
            yield lines
        if not chunk:
            return


def _read_and_tee_loop(
    job_id: str,
    stream: Iterable[str],
    *,
    store: JobStore,
    reports_root: Path | None,
    run_log_writers: dict[str, RunLogWriter],
    pre_marker_buffer: dict[str, list[str]],
    log: LogSink,
    flush_batch: Callable[[str, list[str]], bool],
) -> bool:
    """Flush each read's lines to the job, then tee them to run.log.

    Returns False if the job disappeared mid-stream (a flush found no job
    left in the store) -- the caller must then skip the post-loop drain,
    though its ``finally`` still runs the writer/buffer cleanup.
    """
    try:
        for lines in _iter_line_batches(stream):
            if not flush_batch(job_id, lines):
                return False
            # Tee after flush so a marker in this batch is already applied
            # to the job before we try to resolve run_dir. Skip _cc JSON
            # markers: they are structured IPC, not user-facing terminal
            # output, and leaking them makes the xterm pane noisy.
            for stripped in lines:
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
    pre_marker_buffer.setdefault(job_id, [])
    try:
        if _read_and_tee_loop(
            job_id, stream, store=store, reports_root=reports_root,
            run_log_writers=run_log_writers, pre_marker_buffer=pre_marker_buffer,
            log=log, flush_batch=flush_batch,
        ):
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
