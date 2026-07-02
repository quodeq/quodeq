import io

from quodeq.assistant.adapters._linereader import iter_lines


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
