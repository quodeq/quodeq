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


def test_cli_path_and_api_path_compute_same_cache_key(tmp_path):
    """LOAD-BEARING: the CLI-path's cache writer (constructed inside findings_server
    via _build_router + ServerArgs) MUST produce identical cache keys to the
    API-path's cache writer (constructed inline in _api_runner) for the same
    (file, dim, model, language, ...) inputs.

    Without this, the same file would land in DIFFERENT cache entries depending
    on which path ran first, and incremental runs across mixed paths would
    re-dispatch unnecessarily. This pins the Task 3.5 cross-path consistency
    guarantee against drift in either build_cache_writer caller.
    """
    from quodeq.analysis._types import AnalysisOptions, RunConfig
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.mcp.args import ServerArgs
    from quodeq.analysis.mcp.enricher import CompiledContext
    from quodeq.analysis.mcp.findings_server import _build_router

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")
    cache_root = tmp_path / "cache"

    # Parent-side key (what classify_files_via_cache computes for API path)
    config = RunConfig(
        src=src_root,
        language="kotlin",
        standards_dir=None,
        work_dir=src_root,
        options=AnalysisOptions(subagent_model="sonnet", ai_model="sonnet"),
    )
    parent_key = build_cache_key_for_file(config, "Foo.kt", "flexibility")

    # CLI-path writer (constructed via _build_router + ServerArgs)
    project_dir = tmp_path / "project"
    findings_jsonl = project_dir / "run-1" / "evidence" / "flexibility_evidence.jsonl"
    findings_jsonl.parent.mkdir(parents=True)

    sa = ServerArgs()
    sa.findings_file = str(findings_jsonl)
    sa.dimension = "flexibility"
    sa.work_dir = str(src_root)
    sa.cache_root = str(cache_root)
    sa.model_id = "sonnet"
    sa.language = "kotlin"

    router = _build_router(io.StringIO(), findings_jsonl, CompiledContext(), sa)

    # Trigger the CLI-path's on_file_done with a finding
    router.receive({
        "file": "Foo.kt", "line": 1, "req": "F-ADP-1", "t": "violation",
        "p": "Adaptability", "d": "flexibility", "severity": "major",
        "w": "x", "reason": "x", "snippet": "x",
    })
    router.mark_file_done(file="Foo.kt", status="ok")

    # The CLI-path's cache entry MUST be findable via the parent's key
    cache = LocalFileBackend(root=cache_root)
    entry = cache.get(parent_key)
    assert entry is not None, (
        f"CLI-path cache writer produced a key DIFFERENT from "
        f"build_cache_key_for_file. This breaks cross-path consistency. "
        f"parent_key={parent_key}, cache_root={cache_root}."
    )
    assert entry.file_path == "Foo.kt"
    assert len(entry.findings) == 1


def test_cli_path_and_api_path_agree_with_standards_dir_and_override(tmp_path):
    """LOAD-BEARING (final-review fix): with a real standards dir AND a
    project threshold override in force, the CLI-path cache writer (wired
    the way findings_server.py wires it in production, via ServerArgs
    --standards-dir) MUST key identically to build_cache_key_for_file.

    Regression coverage for the bug where findings_server passed
    server_args.compiled_dir (already ".../compiled") as build_cache_writer's
    standards_dir argument. dimension_params_state then looked for
    ".../compiled/compiled/<dim>.json", found nothing, and silently keyed
    every override-judged entry under the DEFAULT-thresholds key -- poisoning
    the "revert restores old results" guarantee. This test fails on that
    wiring (compiled_dir passed as standards_dir) and passes only when the
    standards ROOT is threaded through via the new --standards-dir arg.
    """
    from quodeq.analysis._types import AnalysisOptions, RunConfig
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.mcp.args import ServerArgs
    from quodeq.analysis.mcp.enricher import CompiledContext
    from quodeq.analysis.mcp.findings_server import _build_router

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "auth.py").write_text("class Auth: pass")
    # A project threshold override -- the exact scenario the bug poisons.
    (src_root / ".quodeq").mkdir()
    (src_root / ".quodeq" / "standards-overrides.json").write_text(
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}'
    )

    standards_dir = tmp_path / "standards"
    (standards_dir / "compiled").mkdir(parents=True)
    (standards_dir / "compiled" / "maintainability.json").write_text(json.dumps({
        "id": "maintainability",
        "principles": [{"name": "P", "requirements": [{
            "id": "M-ANA-2", "text": "Max {max_lines} lines",
            "params": {"max_lines": {"default": 50, "min": 10, "max": 500}},
        }]}],
    }))

    cache_root = tmp_path / "cache"

    # Parent-side key (what classify_files_via_cache computes for the API path)
    config = RunConfig(
        src=src_root,
        language="python",
        standards_dir=standards_dir,
        work_dir=src_root,
        options=AnalysisOptions(subagent_model="sonnet", ai_model="sonnet"),
    )
    parent_key = build_cache_key_for_file(config, "auth.py", "maintainability")

    # CLI-path writer, wired the way findings_server.main() now wires it:
    # --standards-dir is the standards ROOT, not --compiled-dir.
    project_dir = tmp_path / "project"
    findings_jsonl = project_dir / "run-1" / "evidence" / "maintainability_evidence.jsonl"
    findings_jsonl.parent.mkdir(parents=True)

    sa = ServerArgs()
    sa.findings_file = str(findings_jsonl)
    sa.dimension = "maintainability"
    sa.work_dir = str(src_root)
    sa.cache_root = str(cache_root)
    sa.model_id = "sonnet"
    sa.language = "python"
    sa.compiled_dir = str(standards_dir / "compiled")
    sa.standards_dir = str(standards_dir)

    router = _build_router(io.StringIO(), findings_jsonl, CompiledContext(), sa)
    router.receive({
        "file": "auth.py", "line": 1, "req": "M-ANA-2", "t": "violation",
        "p": "Analyzability", "d": "maintainability", "severity": "major",
        "w": "x", "reason": "x", "snippet": "x",
    })
    router.mark_file_done(file="auth.py", status="ok")

    cache = LocalFileBackend(root=cache_root)
    entry = cache.get(parent_key)
    assert entry is not None, (
        "CLI-path cache writer (standards_dir threaded via --standards-dir) "
        "produced a key DIFFERENT from build_cache_key_for_file. If "
        "findings_server regresses to passing compiled_dir as standards_dir, "
        "dimension_params_state silently returns ('', {}) and this entry "
        "lands under the default-thresholds key instead."
    )
    assert entry.file_path == "auth.py"
    assert entry.provenance["effective_params"]["M-ANA-2"]["max_lines"] == 60


def test_cli_path_key_diverges_when_language_missing(tmp_path):
    """Counter-test: when ServerArgs.language is None, the CLI-path's cache
    writer falls back to "" -- which MUST diverge from the API-path key for
    a project where RunConfig.language is set. This pins that the regression
    fixed here cannot silently come back by anyone re-introducing the
    getattr(ctx, "language", None) pattern.
    """
    from quodeq.analysis._types import AnalysisOptions, RunConfig
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.mcp.args import ServerArgs
    from quodeq.analysis.mcp.enricher import CompiledContext
    from quodeq.analysis.mcp.findings_server import _build_router

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")
    cache_root = tmp_path / "cache"

    config = RunConfig(
        src=src_root,
        language="kotlin",
        standards_dir=None,
        work_dir=src_root,
        options=AnalysisOptions(subagent_model="sonnet", ai_model="sonnet"),
    )
    parent_key = build_cache_key_for_file(config, "Foo.kt", "flexibility")

    findings_jsonl = tmp_path / "project" / "run-1" / "evidence" / "flexibility_evidence.jsonl"
    findings_jsonl.parent.mkdir(parents=True)

    sa = ServerArgs()
    sa.findings_file = str(findings_jsonl)
    sa.dimension = "flexibility"
    sa.work_dir = str(src_root)
    sa.cache_root = str(cache_root)
    sa.model_id = "sonnet"
    # sa.language intentionally left as None -- simulates Task 6 not wired yet

    router = _build_router(io.StringIO(), findings_jsonl, CompiledContext(), sa)
    router.receive({
        "file": "Foo.kt", "line": 1, "req": "F-ADP-1", "t": "violation",
        "p": "Adaptability", "d": "flexibility", "severity": "major",
        "w": "x", "reason": "x", "snippet": "x",
    })
    router.mark_file_done(file="Foo.kt", status="ok")

    cache = LocalFileBackend(root=cache_root)
    # Parent key MUST miss when CLI side didn't get the language flag.
    assert cache.get(parent_key) is None, (
        "Expected divergence: when CLI side has no --language, its key must "
        "NOT collide with the API-path key. If this fails, language is no "
        "longer load-bearing in the key composition."
    )
