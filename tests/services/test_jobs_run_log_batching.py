"""Per-read batching of JobManager._consume_stream over pipe-backed and chunked streams."""
from __future__ import annotations

import io
import os
from pathlib import Path

from quodeq.services.jobs import JobManager
from quodeq.services._job_log_tee import _iter_line_batches
from tests.services._jobs_run_log_fixtures import _make_job


# ---------------------------------------------------------------------------
# Per-read batching (finding 5208)
# ---------------------------------------------------------------------------

def _pipe_stream(payload: bytes) -> io.TextIOWrapper:
    """A text stream over a real pipe that already holds *payload*, writer closed.

    Iterables and StringIO cannot show batching: only a pipe-backed
    TextIOWrapper has the byte buffer consume_stream reads per burst.
    """
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    return io.TextIOWrapper(io.open(read_fd, "rb"), encoding="utf-8")


def _spy_flushes(jm: JobManager) -> list[list[str]]:
    flushes: list[list[str]] = []
    real_flush = jm._flush_batch

    def _spy(job_id: str, batch: list[str]) -> bool:
        flushes.append(list(batch))
        return real_flush(job_id, batch)

    jm._flush_batch = _spy
    return flushes


def test_lines_from_one_pipe_read_reach_the_job_in_one_flush(tmp_path: Path) -> None:
    """A burst already sitting in the pipe is flushed as one batch, not per line."""
    lines = [f"line-{i}" for i in range(20)]
    stream = _pipe_stream("".join(f"{line}\n" for line in lines).encode())
    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-pipe"))
    flushes = _spy_flushes(jm)

    with stream:
        jm._consume_stream("job-pipe", stream)

    assert flushes == [lines]
    assert list(jm._store.get("job-pipe").logs) == lines


def test_pipe_reader_keeps_partial_line_and_translates_crlf(tmp_path: Path) -> None:
    """A trailing line without newline waits for EOF and is still delivered;
    CRLF is translated the way the text-mode wrapper would."""
    stream = _pipe_stream(b"first\r\nlast")
    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-tail"))
    flushes = _spy_flushes(jm)

    with stream:
        jm._consume_stream("job-tail", stream)

    assert flushes == [["first"], ["last"]]
    assert list(jm._store.get("job-tail").logs) == ["first", "last"]


class _ChunkedStream:
    """Text-stream stand-in whose byte buffer hands back one scripted chunk
    per read1, the way a pipe returns whatever the child wrote so far."""

    encoding = "utf-8"
    errors = "strict"

    def __init__(self, chunks: list[bytes]) -> None:
        self.buffer = self
        self._chunks = list(chunks)

    def read1(self, _n: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def test_long_unterminated_line_over_many_small_reads_is_delivered_whole() -> None:
    """A 5000-byte line arriving 99 bytes per read (cuts land inside
    multibyte characters) is one line once its newline arrives; the lines
    after it batch and tail as usual."""
    line = "é" * 2500
    payload = line.encode("utf-8") + b"\nsecond\nthird"
    chunks = [payload[i:i + 99] for i in range(0, len(payload), 99)]

    batches = list(_iter_line_batches(_ChunkedStream(chunks)))

    assert batches == [[line, "second"], ["third"]]


def test_crlf_split_across_reads_is_one_newline() -> None:
    """A CR at the end of one read and its LF at the start of the next
    translate to a single newline, as the text wrapper would do."""
    batches = list(_iter_line_batches(_ChunkedStream([b"first\r", b"\nlast\r\n", b"tail"])))

    assert batches == [["first", "last"], ["tail"]]
