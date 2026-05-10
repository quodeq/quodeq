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
