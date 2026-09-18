"""The CLI-path cache writer built by findings_server keys identically to the API path."""
from __future__ import annotations

import io
import json


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


def test_cli_path_key_matches_api_path_when_language_missing(tmp_path):
    """Schema 4: language is provenance, not key. When ServerArgs.language is
    None the CLI-path writer records "" on the entry, and that MUST still
    land on the same key the API path computes for a project whose
    RunConfig.language is set. The old regression (a language mismatch
    between the two paths silently missing every entry) is structurally
    impossible now, and this pins that it stays so.
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
    # Parent key MUST hit even though the CLI side had no language flag.
    entry = cache.get(parent_key)
    assert entry is not None, (
        "Expected convergence: with language out of the key (schema 4), the "
        "CLI-path key must equal the API-path key regardless of --language."
    )
    assert entry.language == ""  # recorded as information, not keyed
