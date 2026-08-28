"""Tests for the API runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis._api_runner import (
    run_api_analysis, ApiRunnerConfig,
    _build_router_context,
    _call_api, _parse_findings, _Finding, _FindingType, _Severity, _LOCAL_TIMEOUT,
)


def _mock_raw_client_finish(content: str, finish_reason: str) -> MagicMock:
    """Mock client whose single choice carries an explicit finish_reason."""
    msg = MagicMock(content=content)
    choice = MagicMock(message=msg, finish_reason=finish_reason)
    response = MagicMock(choices=[choice])
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _make_findings_json(*findings_data) -> str:
    """Build a JSON string of findings from (req, t, file, line, severity, w) tuples."""
    findings = []
    for req, t, file, line, severity, w in findings_data:
        findings.append({
            "req": req, "t": t, "file": file, "line": line,
            "severity": severity, "w": w,
            "snippet": f"line for {req}",
            "reason": f"Test reason for {req}",
        })
    return json.dumps({"findings": findings})


def _mock_raw_client(content: str) -> MagicMock:
    """Build a mock that mimics the raw OpenAI client context manager returning a response."""
    msg = MagicMock(content=content)
    choice = MagicMock(message=msg)
    response = MagicMock(choices=[choice])
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture()
def api_config():
    return ApiRunnerConfig(
        model="test-model",
        api_base="http://localhost:8000/v1",
        api_key="test-key",
    )


class TestResolveTimeout:
    """The read budget scales with the subagent count on local providers.

    Local servers serve one request per loaded model, so with N subagents a
    queued request waits up to (N-1) inferences before its own starts. A fixed
    read budget times out queued-but-healthy calls, burning the whole budget
    for zero findings and feeding the failure-streak breaker.
    """

    def test_local_single_agent_keeps_default(self):
        from quodeq.analysis._api_runner import _resolve_timeout
        cfg = ApiRunnerConfig(model="m", api_base="http://localhost:11434/v1")
        assert _resolve_timeout(cfg, is_openai=False) == _LOCAL_TIMEOUT

    def test_local_read_budget_scales_with_subagents(self):
        from quodeq.analysis._api_runner import _resolve_timeout
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", n_subagents=3,
        )
        t = _resolve_timeout(cfg, is_openai=False)
        assert t.read == _LOCAL_TIMEOUT.read * 3
        assert t.connect == _LOCAL_TIMEOUT.connect
        assert t.write == _LOCAL_TIMEOUT.write
        assert t.pool == _LOCAL_TIMEOUT.pool

    def test_cloud_budget_ignores_subagents(self):
        from quodeq.analysis._api_runner import _resolve_timeout, _CLOUD_TIMEOUT
        cfg = ApiRunnerConfig(
            model="m", api_base="https://api.openai.com/v1", n_subagents=3,
        )
        assert _resolve_timeout(cfg, is_openai=True) == _CLOUD_TIMEOUT

    def test_env_override_wins(self, monkeypatch):
        from quodeq.analysis._api_runner import _resolve_timeout
        monkeypatch.setenv("QUODEQ_API_READ_TIMEOUT", "900")
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", n_subagents=2,
        )
        assert _resolve_timeout(cfg, is_openai=False).read == 900.0

    def test_env_override_garbage_is_ignored(self, monkeypatch):
        from quodeq.analysis._api_runner import _resolve_timeout
        monkeypatch.setenv("QUODEQ_API_READ_TIMEOUT", "soon")
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", n_subagents=2,
        )
        assert _resolve_timeout(cfg, is_openai=False).read == _LOCAL_TIMEOUT.read * 2

    def test_call_api_passes_scaled_timeout_to_client(self):
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:8000/v1",
            api_key="k", n_subagents=2,
        )
        raw_client = _mock_raw_client('{"findings":[]}')
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            _call_api("prompt", cfg)
        timeout = mock_oa.call_args.kwargs["timeout"]
        assert timeout.read == _LOCAL_TIMEOUT.read * 2


class TestRunApiAnalysis:
    """run_api_analysis calls LLM via raw OpenAI client and writes JSONL evidence."""

    def test_writes_jsonl_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(
            ("M-MOD-1", "violation", "main.py", 5, "major", "Multiple responsibilities"),
            ("S-CON-3", "compliance", "utils.py", 1, "minor", "No hardcoded secrets"),
        )
        raw_client = _mock_raw_client(content)

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(prompt="test prompt", jsonl_file=jsonl_file, config=api_config)

        assert jsonl_file.exists()
        lines = [ln for ln in jsonl_file.read_text().strip().split("\n") if ln]
        finding_lines = [json.loads(ln) for ln in lines if "_marker" not in ln]
        assert len(finding_lines) == 2
        assert finding_lines[0]["req"] == "M-MOD-1"
        assert finding_lines[0]["t"] == "violation"
        assert finding_lines[1]["req"] == "S-CON-3"

    def test_passes_model_and_base_url(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = _mock_raw_client('{"findings":[]}')

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(prompt="test prompt", jsonl_file=jsonl_file, config=api_config)

            mock_oa.assert_called_once_with(
                base_url="http://localhost:8000/v1",
                api_key="test-key",
                timeout=_LOCAL_TIMEOUT,
                max_retries=0,
            )

    def test_handles_empty_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = _mock_raw_client('{"findings":[]}')

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(prompt="test prompt", jsonl_file=jsonl_file, config=api_config)

        assert jsonl_file.exists()
        # Only markers (if any), no findings
        lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings_only = [ln for ln in lines if "_marker" not in ln]
        assert findings_only == []

    def test_resolves_short_filenames(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("X-1", "violation", "app.py", 1, "minor", "test"))
        raw_client = _mock_raw_client(content)

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="test", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/myproject/app.py"],
            )

        lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings = [ln for ln in lines if "_marker" not in ln]
        assert len(findings) == 1
        assert findings[0]["file"] == "src/myproject/app.py"

    def test_client_disables_sdk_retries(self, tmp_path, api_config):
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            client = MagicMock()
            client.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"findings":[]}'))]
            )
            mock_oa.return_value.__enter__.return_value = client
            _call_api("prompt", api_config)
        assert mock_oa.call_args.kwargs["max_retries"] == 0


class TestExtraBodyThinkingControls:
    """Ollama only honours `reasoning_effort`; `chat_template_kwargs` is a
    llama.cpp/vLLM convention it silently ignores. Both must go out to local
    providers or Gemma-style thinking loops blow the read timeout."""

    def _create_kwargs(self, cfg):
        raw_client = _mock_raw_client('{"findings":[]}')
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            _call_api("prompt", cfg)
        return raw_client.chat.completions.create.call_args.kwargs

    def test_local_sends_both_thinking_knobs(self, api_config):
        extra = self._create_kwargs(api_config)["extra_body"]
        assert extra["reasoning_effort"] == "none"
        assert extra["chat_template_kwargs"] == {"enable_thinking": False}

    def test_openai_sends_only_reasoning_effort(self):
        cfg = ApiRunnerConfig(
            model="gpt", api_base="https://api.openai.com/v1", api_key="k",
        )
        extra = self._create_kwargs(cfg)["extra_body"]
        assert extra["reasoning_effort"] == "none"
        assert "chat_template_kwargs" not in extra


class TestParserDropAccounting:
    """Every finding-shaped object the model emits but we can't keep must be
    counted, so a systemic loss is visible in the logs instead of silent."""

    def test_counts_finding_missing_req_as_dropped(self):
        # A finding-shaped object missing the required `req`. Today it is
        # silently recursed away and NOT counted; it must count as dropped.
        raw = json.dumps({"findings": [
            {"t": "violation", "file": "a.py", "line": 5, "w": "x",
             "snippet": "code", "reason": "bad"},  # no req
        ]})
        findings, dropped = _parse_findings(raw)
        assert findings == []
        assert dropped == 1

    def test_does_not_count_non_finding_noise(self):
        # A stray container/noise object that does not look like a finding
        # must NOT inflate the dropped count.
        valid = {"req": "R1", "t": "violation", "file": "a.py", "line": 5,
                 "severity": "minor", "w": "x", "snippet": "code", "reason": "bad"}
        raw = '{"note": "analysis complete"}' + json.dumps({"findings": [valid]})
        findings, dropped = _parse_findings(raw)
        assert len(findings) == 1
        assert dropped == 0

    def test_recovers_real_findings_nested_in_finding_shaped_wrapper(self):
        # A wrapper that happens to share >=2 finding field names (severity,
        # reason) but NESTS a real finding must not have that finding swallowed.
        # Counting the wrapper as a drop AND stopping recursion would lose it.
        valid = {"req": "R1", "t": "violation", "file": "a.py", "line": 5,
                 "severity": "minor", "w": "x", "snippet": "code", "reason": "bad"}
        raw = json.dumps({"severity": "major", "reason": "run summary", "items": [valid]})
        findings, dropped = _parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["req"] == "R1"
        assert dropped == 0


class TestFindingVtTaxonomy:
    """The optional 'vt' taxonomy code must survive _Finding validation, or
    every fresh API run scores with taxonomy_used=False (free-text reason
    grouping counts near-duplicates as distinct types and depresses scores)."""

    _BASE = {
        "req": "S-CON-3", "t": "violation", "file": "src/a.py", "line": 3,
        "severity": "critical", "w": "eval usage",
        "snippet": "eval(x)", "reason": "Direct code injection via eval.",
    }

    def test_vt_survives_validate_and_dump(self):
        dumped = _Finding.model_validate({**self._BASE, "vt": "code-injection"}).model_dump()
        assert dumped["vt"] == "code-injection"

    def test_vt_defaults_to_none_when_absent(self):
        dumped = _Finding.model_validate(self._BASE).model_dump()
        assert dumped["vt"] is None


class TestTruncationDetection:
    """A length-truncated response is incomplete: mark the call lossy so the
    file re-dispatches instead of being cached as a clean analysis."""

    def test_truncated_response_is_lossy(self, api_config):
        content = _make_findings_json(
            ("R1", "violation", "a.py", 5, "minor", "x"),
        )
        client = _mock_raw_client_finish(content, "length")
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            _findings, was_lossy = _call_api("prompt", api_config)
        assert was_lossy is True

    def test_complete_response_is_not_lossy(self, api_config):
        content = _make_findings_json(
            ("R1", "violation", "a.py", 5, "minor", "x"),
        )
        client = _mock_raw_client_finish(content, "stop")
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            findings, was_lossy = _call_api("prompt", api_config)
        assert was_lossy is False
        assert len(findings) == 1


class TestMarkerContract:
    """API runner emits file_done markers so the V2 cache can record
    completion. The CLI/MCP path emits these via the agent calling
    `mark_file_done`; the API path is one-shot and emits them itself
    after a clean LLM return.

    Regression: before this, the API runner wrote findings to JSONL
    directly, bypassing FindingsRouter and the marker contract. Cache
    saw zero ok_files for every API run, so cancel-then-restart never
    benefited from prior work. See spec/cancellation design v2.
    """

    def _read_jsonl(self, jsonl_file: Path) -> list[dict]:
        return [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]

    def _findings_only(self, lines: list[dict]) -> list[dict]:
        return [ln for ln in lines if "_marker" not in ln]

    def _markers(self, lines: list[dict]) -> list[dict]:
        return [ln for ln in lines if ln.get("_marker") == "file_done"]

    def test_clean_call_emits_ok_marker_per_source_file(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("M-MOD-1", "violation", "src/a.py", 5, "major", "x"))
        raw_client = _mock_raw_client(content)

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/a.py", "src/b.py", "src/c.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        marked_files = {m["file"] for m in markers}
        assert marked_files == {"src/a.py", "src/b.py", "src/c.py"}
        assert all(m["status"] == "ok" for m in markers)

    def test_clean_call_with_zero_findings_still_marks_files(self, tmp_path, api_config):
        """A clean file (no findings) is still completed analysis -- mark it ok."""
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = _mock_raw_client('{"findings":[]}')

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/clean.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        assert self._findings_only(lines) == []
        markers = self._markers(lines)
        assert len(markers) == 1
        assert markers[0]["file"] == "src/clean.py"
        assert markers[0]["status"] == "ok"

    def test_network_error_emits_error_markers(self, tmp_path, api_config):
        """When the model call fails (was_lossy=True), emit an 'error' marker
        for every file in the batch.

        This makes the failure visible to the failure-streak circuit breaker
        and the post-run model-reachability guard, so an unreachable/broken
        model fails the run loudly instead of silently producing zero findings.
        'error' markers are excluded from the cache's ok_files set, so the
        files still re-dispatch on the next run (retry semantics preserved)."""
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = MagicMock()
        raw_client.chat.completions.create.side_effect = httpx.ReadTimeout("timeout")

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/a.py", "src/b.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        assert {m["file"] for m in markers} == {"src/a.py", "src/b.py"}
        assert all(m["status"] == "error" for m in markers)
        # A failed call produces no findings.
        assert self._findings_only(lines) == []

    def test_truncated_response_emits_error_markers(self, tmp_path, api_config):
        """A length-truncated response is lossy: emit 'error' markers so the
        files re-dispatch and the breaker/reachability guard see the failure,
        while still surfacing the partial findings recovered before the cut."""
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("X-1", "violation", "a.py", 1, "minor", "x"))
        raw_client = _mock_raw_client_finish(content, "length")

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/a.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        assert {m["file"] for m in markers} == {"src/a.py"}
        assert all(m["status"] == "error" for m in markers)
        # Partial findings recovered before the cut are still surfaced.
        assert len(self._findings_only(lines)) == 1

    def test_no_source_files_no_markers(self, tmp_path, api_config):
        """Backward-compat: callers that don't pass source_file_paths get
        finding writes only -- the CLI dim runner is the typical caller and
        that's expected when the whole-dim file list isn't known here."""
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("X-1", "violation", "a.py", 1, "minor", "x"))
        raw_client = _mock_raw_client(content)

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=None,
            )

        lines = self._read_jsonl(jsonl_file)
        assert self._markers(lines) == []
        assert len(self._findings_only(lines)) == 1


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
        from quodeq.analysis._types import AnalysisOptions, RunConfig

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

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="t",
                jsonl_file=jsonl_file,
                config=api_config,
                source_file_paths=["Foo.kt"],
                run_config=run_config,
                dim_id="flexibility",
            )

        entries = list(cache_root.rglob("entry.json"))
        assert len(entries) == 1, (
            f"Expected synchronous cache write on file_done='ok'. "
            f"Found {len(entries)} entries under {cache_root}."
        )


class TestDropStatsRecording:
    """_call_api feeds the per-run drop-ratio accumulator (issue #606).

    The per-call WARNING already counts dropped findings; recording the same
    (dropped, kept) pair into ``_drop_stats`` lets the run loop surface ONE
    aggregate signal instead of N scattered lines.
    """

    @pytest.fixture(autouse=True)
    def _reset_accumulator(self):
        from quodeq.analysis import _drop_stats
        _drop_stats.consume()
        yield
        _drop_stats.consume()

    def test_call_with_malformed_finding_records_drop_and_kept(self, api_config):
        from quodeq.analysis import _drop_stats
        valid = {"req": "R1", "t": "violation", "file": "a.py", "line": 5,
                 "severity": "minor", "w": "x", "snippet": "code", "reason": "bad"}
        malformed = {"t": "violation", "file": "b.py", "line": 1, "w": "y",
                     "snippet": "code", "reason": "bad"}  # no req -> dropped
        content = json.dumps({"findings": [valid, malformed]})
        client = _mock_raw_client(content)
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            _call_api("prompt", api_config)
        stats = _drop_stats.consume()
        assert stats.dropped == 1
        assert stats.kept == 1

    def test_failed_call_records_nothing(self, api_config):
        from quodeq.analysis import _drop_stats
        client = MagicMock()
        client.chat.completions.create.side_effect = httpx.ReadTimeout("timeout")
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            _call_api("prompt", api_config)
        assert _drop_stats.consume().parsed == 0


class TestApiRunnerConfig:
    """ApiRunnerConfig dataclass."""

    def test_defaults(self):
        cfg = ApiRunnerConfig(model="test", api_base="http://localhost/v1")
        assert cfg.api_key == ""
        assert cfg.temperature == 0.1
        assert cfg.max_tokens is None

    def test_custom_values(self):
        cfg = ApiRunnerConfig(
            model="gpt-4o",
            api_base="https://api.openai.com/v1",
            api_key="sk-...",
            temperature=0.0,
            max_tokens=4096,
        )
        assert cfg.temperature == 0.0
        assert cfg.max_tokens == 4096


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
        from quodeq.llm_bridge._embeddings import reset_embedding_availability_cache

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
