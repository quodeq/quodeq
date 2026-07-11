import io

from quodeq.assistant.adapters._linereader import _CHUNK, iter_lines


def test_yields_complete_lines():
    stream = io.StringIO("line1\nline2\nline3\n")
    assert list(iter_lines(stream)) == ["line1", "line2", "line3"]


def test_flushes_trailing_partial_line():
    stream = io.StringIO("a\nb\nno-newline-tail")
    assert list(iter_lines(stream)) == ["a", "b", "no-newline-tail"]


def test_handles_lines_split_across_chunks():
    stream = io.StringIO("hello world\nsecond\n")
    assert list(iter_lines(stream, chunk_size=4)) == ["hello world", "second"]


def test_empty_stream():
    assert list(iter_lines(io.StringIO(""))) == []


def test_oversized_newline_less_run_is_bounded_not_hung():
    # A stream that never sends a newline must not grow the buffer without
    # bound -- once past max_line it should be flushed as its own piece so
    # iteration terminates and memory stays bounded.
    total = (1 << 20) * 3 + 100  # a bit over 3x the 1 MiB default cap
    stream = io.StringIO("x" * total)
    pieces = list(iter_lines(stream, max_line=1 << 20))
    assert pieces  # terminated and yielded something
    assert all(len(p) <= (1 << 20) + _CHUNK for p in pieces)
    assert sum(len(p) for p in pieces) == total
