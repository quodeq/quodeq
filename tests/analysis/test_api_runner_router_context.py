"""API runner router wiring: synchronous cache writes and _build_router_context seams."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis._api_runner import (
    ApiAnalysisRequest,
    _build_router_context,
    run_api_analysis,
)

from ._api_runner_helpers import _make_findings_json, _mock_raw_client


class TestSyncCacheWrite:
    """API path wires build_cache_writer into FindingsRouter so each
    ``mark_file_done(status='ok')`` triggers a synchronous cache.put.

    Closes the 30s polling window between watcher ticks: after this, the
    API runner's in-process router writes its per-file cache entry on disk
    BEFORE returning from ``mark_file_done``. SIGKILL between the JSONL
    marker and the cache put cannot lose the work.
    """

    def test_api_path_writes_cache_synchronously_when_file_done_ok(
        self, tmp_path, api_config, monkeypatch,
    ):
        """After router processes findings + mark_file_done(file=F, status='ok')
        in the API path, a cache entry for F exists on disk under cache_root.
        """
        from quodeq.analysis.run_types import AnalysisOptions, RunConfig

        src_root = tmp_path / "src"
        src_root.mkdir()
        (src_root / "Foo.kt").write_text("class Foo")

        # default_cache_root() honours QUODEQ_CACHE_ROOT (Fix A, #2419/#2340),
        # so redirect via that env var to keep this test self-contained.
        fake_cache_base = tmp_path / "cache"
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(fake_cache_base))
        cache_root = fake_cache_base / "results"

        run_config = RunConfig(
            src=src_root,
            language="kotlin",
            standards_dir=None,
            work_dir=src_root,
            options=AnalysisOptions(subagent_model="sonnet"),
        )

        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("M-MOD-1", "violation", "Foo.kt", 1, "minor", "x"))
        raw_client = _mock_raw_client(content)

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="t",
                    jsonl_file=jsonl_file,
                    source_file_paths=["Foo.kt"],
                    run_config=run_config,
                    dim_id="flexibility",
                ),
                config=api_config,
            )

        entries = list(cache_root.rglob("entry.json"))
        assert len(entries) == 1, (
            f"Expected synchronous cache write on file_done='ok'. "
            f"Found {len(entries)} entries under {cache_root}."
        )


class TestBuildRouterContextDegradesOnEnrichmentSetupFailure:
    def test_unreadable_compiled_standards_degrades_to_none(self, tmp_path, monkeypatch, caplog):
        """_build_router_context's except narrows to (OSError, json.JSONDecodeError):
        a failure loading compiled refs/requirements must still degrade to
        raw-findings mode (ctx=None), not abort the run."""
        import logging

        def boom(*_a, **_kw):
            raise OSError("disk read failed")

        monkeypatch.setattr("quodeq.analysis._api_runner.load_compiled_refs", boom)

        with caplog.at_level(logging.WARNING, logger="quodeq.analysis._api_runner"):
            ctx = _build_router_context(
                tmp_path, "security", None, tmp_path, tmp_path / "run-1",
            )

        assert ctx is None
        assert any("Could not build enrichment context" in r.message for r in caplog.records)

    def test_malformed_compiled_standards_json_degrades_to_none(self, tmp_path, monkeypatch):
        """Same contract for the other tuple member: a compiled-standards
        read that raises json.JSONDecodeError must also degrade, not abort."""
        import json

        def boom(*_a, **_kw):
            raise json.JSONDecodeError("bad json", "doc", 0)

        monkeypatch.setattr("quodeq.analysis._api_runner.load_compiled_requirements", boom)

        ctx = _build_router_context(
            tmp_path, "security", None, tmp_path, tmp_path / "run-1",
        )

        assert ctx is None


class TestBuildRouterContextCorpus:
    """`_build_router_context` wires precedent_corpus (env-gated, never raises)."""

    def test_corpus_none_when_flag_off(self, tmp_path, monkeypatch):
        monkeypatch.delenv("QUODEQ_SEMANTIC_PRECEDENTS", raising=False)

        ctx = _build_router_context(
            tmp_path, "security", None, tmp_path, tmp_path / "run-1",
        )

        assert ctx is not None
        assert ctx.precedent_corpus is None

    def test_corpus_degrades_when_flag_on_but_no_embedder(self, tmp_path, monkeypatch):
        from quodeq.llm_bridge.embeddings import reset_embedding_availability_cache

        reset_embedding_availability_cache()
        monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
        monkeypatch.setenv("QUODEQ_EMBEDDING_BASE_URL", "http://127.0.0.1:1")  # nothing listens

        ctx = _build_router_context(
            tmp_path, "security", None, tmp_path, tmp_path / "run-1",
        )

        assert ctx is not None
        assert ctx.precedent_corpus is None

    def test_wires_load_precedent_corpus_with_project_and_run_dir(self, tmp_path, monkeypatch):
        """Proves `_build_router_context` actually calls load_precedent_corpus
        with (project_dir, run_dir) and stores its return value -- the
        None-when-flag-off test above passes trivially against the
        CompiledContext field default, so this closes that gap."""
        import quodeq.analysis._api_runner as api_runner_module

        sentinel = object()
        calls = []

        def fake_load_precedent_corpus(project_dir, run_dir):
            calls.append((project_dir, run_dir))
            return sentinel

        monkeypatch.setattr(
            api_runner_module, "load_precedent_corpus", fake_load_precedent_corpus,
        )

        run_dir = tmp_path / "run-1"
        ctx = _build_router_context(tmp_path, "security", None, tmp_path, run_dir)

        assert calls == [(tmp_path, run_dir)]
        assert ctx.precedent_corpus is sentinel


class TestBuildRouterContextPrecedentReader:
    def test_wires_the_strict_dismissed_reader(self, tmp_path, monkeypatch):
        """The best-effort reader turns a failed DB open into [], which the
        per-run memo would remember as "no dismissals" until that DB's stat
        changes. The strict reader lets load_precedent_fingerprints see the
        failure, log it and skip the run without memoizing."""
        import quodeq.analysis._api_runner as api_runner_module
        from quodeq.data.sqlite.findings_queries import (
            dismissed_source_stamp, read_dismissed_snippets_strict,
        )

        seams: dict = {}

        def fake_load_precedent_fingerprints(project_dir, **kwargs):
            seams.update(kwargs)
            return {"fp"}

        monkeypatch.setattr(
            api_runner_module, "load_precedent_fingerprints",
            fake_load_precedent_fingerprints,
        )

        ctx = _build_router_context(tmp_path, "security", None, tmp_path, tmp_path / "run-1")

        assert seams["read_dismissed"] is read_dismissed_snippets_strict
        assert seams["source_stamp"] is dismissed_source_stamp
        assert ctx.precedent_fingerprints == {"fp"}
