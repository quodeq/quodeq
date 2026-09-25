"""Extended tests for _command.py: _build_mcp_server_args flags and cache-root resolution."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._command import _build_mcp_server_args
from quodeq.analysis._config import AnalysisConfig


# ---------------------------------------------------------------------------
# _build_mcp_server_args
# ---------------------------------------------------------------------------

class TestBuildMcpServerArgs:
    def test_basic_args(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config)
        assert str(jsonl.resolve()) in args

    def test_includes_compiled_dir_and_dimension(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        compiled = tmp_path / "compiled"
        config = AnalysisConfig(jsonl_file=jsonl, compiled_dir=compiled, dimension="security")
        args = _build_mcp_server_args(config)
        assert "--compiled-dir" in args
        assert "--dimension" in args
        assert "security" in args

    def test_includes_queue(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        queue = tmp_path / "queue.json"
        config = AnalysisConfig(jsonl_file=jsonl, queue_path=queue)
        args = _build_mcp_server_args(config)
        assert "--queue" in args

    def test_includes_agent_id(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, agent_id="agent-1")
        args = _build_mcp_server_args(config)
        assert "--agent-id" in args
        assert "agent-1" in args

    def test_skip_agent_id(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, agent_id="agent-1")
        args = _build_mcp_server_args(config, skip_agent_id=True)
        assert "--agent-id" not in args

    def test_includes_work_dir(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, work_dir=tmp_path)
        args = _build_mcp_server_args(config)
        assert "--work-dir" in args

    def test_work_dir_fallback(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config, work_dir=tmp_path)
        assert "--work-dir" in args

    def test_includes_cache_root_model_id_language(self, tmp_path):
        """#6: the args list passed to findings_server.py MUST include
        --cache-root, --model-id, and --language so the subprocess can build a
        cache writer with the same fingerprint inputs as the parent's
        classify_files_via_cache. Without these flags, CLI-path and API-path
        cache keys diverge for the same project state.
        """
        from types import SimpleNamespace

        jsonl = tmp_path / "findings.jsonl"
        # Synthesise a minimal RunConfig-shaped carrier the helper can read.
        run_config = SimpleNamespace(
            language="kotlin",
            options=SimpleNamespace(subagent_model="sonnet", ai_model="opus"),
        )
        config = AnalysisConfig(
            jsonl_file=jsonl, run_config=run_config, cache_root=tmp_path / "cache" / "results",
        )
        args = _build_mcp_server_args(config)

        assert "--cache-root" in args
        assert "--model-id" in args
        assert "--language" in args
        # Values
        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "sonnet"
        lang_idx = args.index("--language")
        assert args[lang_idx + 1] == "kotlin"
        # The run's resolved cache root travels verbatim.
        cr_idx = args.index("--cache-root")
        assert args[cr_idx + 1] == str(tmp_path / "cache" / "results")

    def test_cache_flags_fall_back_when_no_run_config(self, tmp_path):
        """Without a RunConfig carrier, --cache-root is emitted because this
        config sets cache_root directly (it's omitted when cache_root is
        None), model_id comes from AnalysisConfig.ai_model, and language is
        empty — matching the contract that language="" means "unset" rather
        than missing.
        """
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, ai_model="haiku", cache_root=tmp_path / "c")
        args = _build_mcp_server_args(config)

        assert "--cache-root" in args
        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "haiku"
        lang_idx = args.index("--language")
        assert args[lang_idx + 1] == ""

    def test_model_id_falls_back_to_unknown(self, tmp_path):
        """No ai_model and no run_config => model_id is 'unknown' (reference
        from cache.dimension_helpers.model_id_from).
        """
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config)

        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "unknown"

    def test_includes_standards_dir_from_run_config(self, tmp_path):
        """Final-review fix: the cli-register path (e.g. Gemini) must also
        emit --standards-dir from RunConfig.standards_dir -- the standards
        ROOT, not AnalysisConfig.compiled_dir (which is already
        standards_dir/"compiled"). Without this, the same params-fingerprint
        bug findings_server.py had would resurface for cli-register providers.
        """
        from types import SimpleNamespace

        jsonl = tmp_path / "findings.jsonl"
        standards_dir = tmp_path / "standards"
        run_config = SimpleNamespace(
            language="kotlin",
            standards_dir=standards_dir,
            options=SimpleNamespace(subagent_model="sonnet", ai_model="opus"),
        )
        compiled = standards_dir / "compiled"
        config = AnalysisConfig(
            jsonl_file=jsonl, compiled_dir=compiled, dimension="security",
            run_config=run_config,
        )
        args = _build_mcp_server_args(config)

        assert "--standards-dir" in args
        sd_idx = args.index("--standards-dir")
        assert args[sd_idx + 1] == str(standards_dir.resolve())
        # Sanity: distinct from --compiled-dir's value (the bug this guards
        # against conflated the two).
        cd_idx = args.index("--compiled-dir")
        assert args[cd_idx + 1] != args[sd_idx + 1]

    def test_standards_dir_absent_without_run_config(self, tmp_path):
        """No RunConfig carrier => --standards-dir is omitted entirely (not
        emitted as empty/None), matching the other run_config-derived flags'
        omission pattern in this file.
        """
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config)

        assert "--standards-dir" not in args


# ---------------------------------------------------------------------------
# Fix A (#2419): the cache root is the run's resolved one, never re-read here.
# QUODEQ_CACHE_ROOT reaching the spawn through run_analysis is pinned in
# tests/analysis/test_run_env_settings.py.
# ---------------------------------------------------------------------------

class TestBuildMcpServerArgsCacheRootEnv:
    def test_cache_root_comes_from_the_config_not_the_env(self, tmp_path, monkeypatch):
        """The config's cache root is forwarded; an exported QUODEQ_CACHE_ROOT
        is not consulted by the builder itself."""
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, ai_model="test-model", cache_root=tmp_path / "results")
        args = _build_mcp_server_args(config)

        cr_idx = args.index("--cache-root")
        resolved = Path(args[cr_idx + 1])
        assert resolved == tmp_path / "results"
