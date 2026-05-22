"""End-to-end test for the CLI path's synchronous cache write.

Spawns findings_server.py as a real subprocess (matching production) and
verifies that report_finding + mark_file_done(status='ok') results in a
cache entry on disk before the MCP response returns.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _make_jsonrpc(method: str, params: dict, msg_id: int) -> bytes:
    """Frame a JSON-RPC 2.0 request for the findings_server stdio protocol."""
    return (json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}) + "\n").encode()


def _findings_server_path() -> Path:
    """Return the on-disk path to findings_server.py via its module __file__."""
    import quodeq.analysis.mcp.findings_server as _fs
    return Path(_fs.__file__)


def test_findings_server_writes_cache_via_mcp(tmp_path):
    """Subprocess findings_server with --cache-root + --model-id writes a
    cache entry when it receives mark_file_done(status='ok')."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    # findings_path layout: <project_dir>/<run_id>/evidence/<dim>_evidence.jsonl
    project_dir = tmp_path / "project"
    run_dir = project_dir / "run-1"
    jsonl = run_dir / "evidence" / "flexibility_evidence.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.touch()

    proc = subprocess.Popen(
        [
            sys.executable, str(_findings_server_path()), str(jsonl),
            "--dimension", "flexibility",
            "--work-dir", str(src_root),
            "--cache-root", str(cache_root),
            "--model-id", "sonnet",
        ],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    try:
        # Send report_finding for Foo.kt
        finding = {
            "file": "Foo.kt", "line": 10,
            "req": "F-ADP-1", "t": "violation",
            "p": "Adaptability", "d": "flexibility",
            "severity": "major", "w": "test finding",
            "reason": "test", "snippet": "code",
        }
        proc.stdin.write(_make_jsonrpc("tools/call", {
            "name": "report_finding", "arguments": finding,
        }, 1))
        proc.stdin.flush()

        # Send mark_file_done(Foo.kt, ok)
        proc.stdin.write(_make_jsonrpc("tools/call", {
            "name": "mark_file_done", "arguments": {"file": "Foo.kt", "status": "ok"},
        }, 2))
        proc.stdin.flush()

        # Read two responses (one per request)
        for _ in range(2):
            line = proc.stdout.readline()
            assert line, f"server unexpectedly closed stdout; stderr={proc.stderr.read().decode()}"
            resp = json.loads(line)
            assert "error" not in resp, f"server error: {resp}"

        # By the time mark_file_done returned, the cache entry must exist.
        entries = list(cache_root.rglob("entry.json"))
        assert len(entries) == 1, (
            f"Expected 1 cache entry under {cache_root}, got {len(entries)}. "
            "Synchronous cache write didn't fire."
        )
        entry_data = json.loads(entries[0].read_text())
        assert entry_data["file_path"] == "Foo.kt"
        assert len(entry_data["findings"]) == 1
        assert entry_data["findings"][0]["p"] == "Adaptability"
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)


def test_findings_server_raises_when_dimension_set_without_cache_args(tmp_path):
    """When --dimension is set but --cache-root and --model-id are missing,
    the subprocess MUST exit with an error (hard-fail, defense-in-depth)."""
    jsonl = tmp_path / "project" / "run-1" / "evidence" / "flexibility_evidence.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.touch()

    proc = subprocess.run(
        [sys.executable, str(_findings_server_path()), str(jsonl), "--dimension", "flexibility"],
        capture_output=True, timeout=10,
    )

    assert proc.returncode != 0, (
        f"Expected non-zero exit; stdout={proc.stdout.decode()} stderr={proc.stderr.decode()}"
    )
    stderr = proc.stderr.decode()
    assert "cache-root" in stderr or "model-id" in stderr or "cache_root" in stderr or "model_id" in stderr, (
        f"Expected an explanatory error mentioning the missing args; got:\n{stderr}"
    )


def test_build_router_constructs_cache_writer_when_args_present(tmp_path):
    """_build_router wires a cache writer into the router when ServerArgs
    has cache_root + model_id + dimension."""
    from quodeq.analysis.mcp.findings_server import _build_router
    from quodeq.analysis.mcp.enricher import CompiledContext
    from quodeq.analysis.mcp.args import ServerArgs

    project_dir = tmp_path / "project"
    findings_path = project_dir / "run-1" / "evidence" / "flexibility_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)

    sa = ServerArgs()
    sa.dimension = "flexibility"
    sa.cache_root = str(tmp_path / "cache")
    sa.model_id = "sonnet"
    sa.work_dir = str(tmp_path / "src")
    (tmp_path / "src").mkdir()

    router = _build_router(io.StringIO(), findings_path, CompiledContext(), sa)

    assert router._on_file_done is not None, "Expected on_file_done to be wired"


def test_build_router_raises_when_dimension_set_without_cache_args(tmp_path):
    """_build_router hard-fails when --dimension is set but cache args missing."""
    from quodeq.analysis.mcp.findings_server import _build_router
    from quodeq.analysis.mcp.enricher import CompiledContext
    from quodeq.analysis.mcp.args import ServerArgs

    project_dir = tmp_path / "project"
    findings_path = project_dir / "run-1" / "evidence" / "flexibility_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)

    sa = ServerArgs()
    sa.dimension = "flexibility"
    # cache_root and model_id intentionally absent

    with pytest.raises(RuntimeError) as exc_info:
        _build_router(io.StringIO(), findings_path, CompiledContext(), sa)

    msg = str(exc_info.value)
    assert "cache-root" in msg or "cache_root" in msg
    assert "model-id" in msg or "model_id" in msg


def test_build_router_no_cache_writer_when_dimension_absent(tmp_path):
    """No --dimension means watcher-only mode: no cache writer is attached."""
    from quodeq.analysis.mcp.findings_server import _build_router
    from quodeq.analysis.mcp.enricher import CompiledContext
    from quodeq.analysis.mcp.args import ServerArgs

    project_dir = tmp_path / "project"
    findings_path = project_dir / "run-1" / "evidence" / "flexibility_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)

    sa = ServerArgs()
    # No dimension, no cache args

    router = _build_router(io.StringIO(), findings_path, CompiledContext(), sa)

    assert router._on_file_done is None
