import io
import os
import threading

from quodeq.assistant.adapters._linereader import iter_lines
from tests._timeouts import budget


def test_yields_complete_lines():
    stream = io.StringIO("line1\nline2\nline3\n")
    assert list(iter_lines(stream)) == ["line1", "line2", "line3"]


def test_flushes_trailing_partial_line():
    stream = io.StringIO("a\nb\nno-newline-tail")
    assert list(iter_lines(stream)) == ["a", "b", "no-newline-tail"]


def test_empty_stream():
    assert list(iter_lines(io.StringIO(""))) == []


def test_yields_line_while_stream_still_open():
    # A live subprocess pipe delivers lines long before EOF. The reader must
    # yield each complete line as soon as it arrives, NOT block until the
    # process exits: TextIOWrapper.read(n) is greedy (waits for n chars or
    # EOF), which turns a whole streamed turn into one end-of-process burst.
    rfd, wfd = os.pipe()
    reader = os.fdopen(rfd, "r", encoding="utf-8")
    writer = os.fdopen(wfd, "w", encoding="utf-8")
    got = []
    first_line = threading.Event()

    def consume():
        for line in iter_lines(reader):
            got.append(line)
            first_line.set()
            return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    try:
        writer.write('{"type":"token"}\n')
        writer.flush()
        assert first_line.wait(timeout=budget(5)), \
            "line was not yielded while the pipe was still open (reader waits for EOF)"
        assert got == ['{"type":"token"}']
    finally:
        writer.close()
        t.join(timeout=budget(5))
        reader.close()


def test_oversized_newline_less_run_is_bounded_not_hung():
    # A stream that never sends a newline must not grow the buffer without
    # bound -- once past max_line it should be flushed as its own piece so
    # iteration terminates and memory stays bounded.
    total = (1 << 20) * 3 + 100  # a bit over 3x the 1 MiB default cap
    stream = io.StringIO("x" * total)
    pieces = list(iter_lines(stream, max_line=1 << 20))
    assert pieces  # terminated and yielded something
    assert all(len(p) <= (1 << 20) for p in pieces)
    assert sum(len(p) for p in pieces) == total
