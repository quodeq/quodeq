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


def test_router_accumulates_findings_per_file_then_drains_on_ok():
    """Receive 3 findings for Foo.kt and 2 for Bar.kt. Call mark_file_done(Foo.kt, ok).
    Callback fires with ('Foo.kt', [3 enriched finding dicts]); _findings_by_file
    no longer contains Foo.kt; Bar.kt's findings still accumulated."""
    import io
    from quodeq.analysis.mcp.router import FindingsRouter
    from quodeq.analysis.mcp.enricher import CompiledContext

    calls: list[tuple[str, list[dict]]] = []
    def on_file_done(file: str, findings: list[dict]) -> None:
        calls.append((file, findings))

    fh = io.StringIO()
    router = FindingsRouter(
        fh, context=CompiledContext(), on_file_done=on_file_done,
    )
    for i in range(3):
        router.receive({
            "file": "Foo.kt", "line": 10 + i,
            "req": f"F-ADP-{i}", "t": "violation",
            "p": "Adaptability", "d": "flexibility",
            "severity": "major", "w": f"finding {i}",
            "reason": "test", "snippet": "code",
        })
    for i in range(2):
        router.receive({
            "file": "Bar.kt", "line": 20 + i,
            "req": f"F-RPL-{i}", "t": "violation",
            "p": "Replaceability", "d": "flexibility",
            "severity": "major", "w": f"finding {i}",
            "reason": "test", "snippet": "code",
        })

    router.mark_file_done(file="Foo.kt", status="ok")

    assert len(calls) == 1
    file, findings = calls[0]
    assert file == "Foo.kt"
    assert len(findings) == 3
    assert "Foo.kt" not in router._findings_by_file
    assert len(router._findings_by_file["Bar.kt"]) == 2


def test_router_discards_findings_on_mark_file_done_error():
    """When mark_file_done is called with status='error', accumulated findings
    are popped and dropped — callback is NOT called."""
    import io
    from quodeq.analysis.mcp.router import FindingsRouter
    from quodeq.analysis.mcp.enricher import CompiledContext

    calls: list[tuple[str, list[dict]]] = []
    def on_file_done(file: str, findings: list[dict]) -> None:
        calls.append((file, findings))

    fh = io.StringIO()
    router = FindingsRouter(
        fh, context=CompiledContext(), on_file_done=on_file_done,
    )
    router.receive({
        "file": "Bar.kt", "line": 1,
        "req": "F-ADP-1", "t": "violation",
        "p": "Adaptability", "d": "flexibility",
        "severity": "major", "w": "finding", "reason": "test", "snippet": "code",
    })
    router.mark_file_done(file="Bar.kt", status="error")

    assert calls == []
    assert "Bar.kt" not in router._findings_by_file


def test_router_callback_exception_does_not_break_marker_write_or_accumulation():
    """A raising on_file_done callback must not prevent the file_done marker
    from reaching the JSONL, and must still clear _findings_by_file."""
    import io
    from quodeq.analysis.mcp.router import FindingsRouter
    from quodeq.analysis.mcp.enricher import CompiledContext

    def boom(_file: str, _findings: list[dict]) -> None:
        raise RuntimeError("simulated cache write failure")

    fh = io.StringIO()
    router = FindingsRouter(fh, context=CompiledContext(), on_file_done=boom)
    router.receive({
        "file": "Foo.kt", "line": 1,
        "req": "F-ADP-1", "t": "violation",
        "p": "Adaptability", "d": "flexibility",
        "severity": "major", "w": "finding", "reason": "test", "snippet": "code",
    })
    router.mark_file_done(file="Foo.kt", status="ok")

    output = fh.getvalue()
    assert '"_marker": "file_done"' in output
    assert '"file": "Foo.kt"' in output
    assert '"status": "ok"' in output
    assert "Foo.kt" not in router._findings_by_file


def test_router_skips_accumulation_when_no_callback():
    """When on_file_done is None, _findings_by_file is never populated
    (memory optimization)."""
    import io
    from quodeq.analysis.mcp.router import FindingsRouter
    from quodeq.analysis.mcp.enricher import CompiledContext

    fh = io.StringIO()
    router = FindingsRouter(fh, context=CompiledContext(), on_file_done=None)
    router.receive({
        "file": "Foo.kt", "line": 1,
        "req": "F-ADP-1", "t": "violation",
        "p": "Adaptability", "d": "flexibility",
        "severity": "major", "w": "finding", "reason": "test", "snippet": "code",
    })

    assert "Foo.kt" not in router._findings_by_file
    assert '"file": "Foo.kt"' in fh.getvalue()
