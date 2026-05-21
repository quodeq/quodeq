from __future__ import annotations
import io
import json

import pytest

from quodeq.analysis.mcp.router import FindingsRouter


def _make_router(fh: io.StringIO) -> FindingsRouter:
    return FindingsRouter(fh)


def _read_lines(fh: io.StringIO) -> list[dict]:
    return [json.loads(ln) for ln in fh.getvalue().splitlines() if ln.strip()]


class TestMarkFileDone:
    def test_writes_ok_marker(self):
        fh = io.StringIO()
        router = _make_router(fh)
        router.mark_file_done(file="src/foo.py", status="ok")
        lines = _read_lines(fh)
        assert len(lines) == 1
        assert lines[0]["_marker"] == "file_done"
        assert lines[0]["file"] == "src/foo.py"
        assert lines[0]["status"] == "ok"

    def test_writes_error_marker_with_reason(self):
        fh = io.StringIO()
        router = _make_router(fh)
        router.mark_file_done(file="src/bar.py", status="error", reason="token_limit")
        lines = _read_lines(fh)
        assert lines[0]["status"] == "error"
        assert lines[0]["reason"] == "token_limit"

    def test_marker_does_not_dedupe_with_findings(self):
        fh = io.StringIO()
        router = _make_router(fh)
        router.receive({
            "req": "M-MOD-1", "t": "violation", "file": "src/foo.py",
            "line": 10, "severity": "minor", "w": "x", "reason": "y",
        })
        router.mark_file_done(file="src/foo.py", status="ok")
        lines = _read_lines(fh)
        assert len(lines) == 2
        assert "_marker" not in lines[0]
        assert lines[1]["_marker"] == "file_done"

    def test_invalid_status_rejected(self):
        fh = io.StringIO()
        router = _make_router(fh)
        with pytest.raises(ValueError):
            router.mark_file_done(file="src/foo.py", status="bogus")


def test_mark_file_done_invokes_on_file_done_callback_when_ok():
    """When mark_file_done is called with status='ok', the on_file_done
    callback is invoked with the file path. status='error' does not
    invoke the callback."""
    import io
    from quodeq.analysis.mcp.router import FindingsRouter

    calls = []
    def on_file_done(file: str) -> None:
        calls.append(file)

    fh = io.StringIO()
    router = FindingsRouter(fh, on_file_done=on_file_done)

    router.mark_file_done(file="Foo.kt", status="ok")
    router.mark_file_done(file="Bar.kt", status="error")
    router.mark_file_done(file="Baz.kt", status="ok")

    assert calls == ["Foo.kt", "Baz.kt"]


def test_mark_file_done_callback_exception_does_not_break_marker_write():
    """A raising on_file_done callback must not prevent the file_done
    marker from reaching the JSONL. Cache failures must never roll back
    the worker's completion record."""
    import io
    from quodeq.analysis.mcp.router import FindingsRouter

    def boom(_file: str) -> None:
        raise RuntimeError("simulated cache write failure")

    fh = io.StringIO()
    router = FindingsRouter(fh, on_file_done=boom)
    router.mark_file_done(file="Foo.kt", status="ok")
    assert '"_marker": "file_done"' in fh.getvalue()
    assert '"file": "Foo.kt"' in fh.getvalue()
    assert '"status": "ok"' in fh.getvalue()
