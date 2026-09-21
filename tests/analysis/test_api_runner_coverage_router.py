"""Extended tests for _api_runner.py: path resolution, router context, append and cache root."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis._api_runner import (
    ApiAnalysisRequest,
    ApiRunnerConfig,
    _build_router_context,
    _resolve_file_paths,
    run_api_analysis,
)


# ---------------------------------------------------------------------------
# _resolve_file_paths
# ---------------------------------------------------------------------------

class TestResolveFilePaths:
    def test_resolves_short_name_to_full_path(self):
        findings = [{"file": "app.py", "req": "X-1"}]
        source_paths = ["src/myproject/app.py", "src/myproject/utils.py"]
        result = _resolve_file_paths(findings, source_paths)
        assert result[0]["file"] == "src/myproject/app.py"

    def test_leaves_full_paths_unchanged(self):
        findings = [{"file": "src/myproject/app.py", "req": "X-1"}]
        source_paths = ["src/myproject/app.py"]
        result = _resolve_file_paths(findings, source_paths)
        assert result[0]["file"] == "src/myproject/app.py"

    def test_leaves_unknown_names_unchanged(self):
        findings = [{"file": "unknown.py", "req": "X-1"}]
        source_paths = ["src/myproject/app.py"]
        result = _resolve_file_paths(findings, source_paths)
        assert result[0]["file"] == "unknown.py"

    def test_handles_empty_file_field(self):
        findings = [{"file": "", "req": "X-1"}]
        result = _resolve_file_paths(findings, ["src/app.py"])
        assert result[0]["file"] == ""

    def test_handles_missing_file_field(self):
        findings = [{"req": "X-1"}]
        result = _resolve_file_paths(findings, ["src/app.py"])
        assert "file" not in result[0] or result[0].get("file", "") == ""


# ---------------------------------------------------------------------------
# _build_router_context
# ---------------------------------------------------------------------------

class TestBuildRouterContext:
    def test_returns_none_without_compiled_dir(self):
        """Without a compiled standards dir there is no enrichment context to
        build. Callers fall back to a default-context router (still emits
        markers and writes findings, just no req-ref enrichment)."""
        assert _build_router_context(None, None, None, None, None) is None

    def test_returns_none_on_load_failure(self):
        """A broken compiled dir must not propagate -- the API runner needs
        to keep writing findings + markers even when enrichment fails."""
        with patch("quodeq.analysis._api_runner.load_compiled_refs",
                   side_effect=OSError("boom")):
            ctx = _build_router_context(Path("/nonexistent"), "security", None, None, None)
        assert ctx is None

    def test_resolves_declared_trust_model_from_work_dir(self, tmp_path):
        """``_build_router_context``'s ``resolve_trust_model(work_dir)`` call
        is one of three live wiring points for the declared trust model.
        Nothing failed when a reviewer
        set all three to None at once and the full suite stayed green -- this
        closes that gap by exercising _build_router_context directly against
        a real declared profile, using a compiled_dir/dimension combination
        that never touches disk for standards loading (dimension=None short-
        circuits _load_compiled_data), so only the trust_model line is
        exercised for real.
        """
        profile_dir = tmp_path / ".quodeq"
        profile_dir.mkdir()
        (profile_dir / "project-profile.json").write_text(json.dumps({
            "version": 1, "multiTenant": False, "networkExposure": "loopback",
        }))

        ctx = _build_router_context(
            Path("/nonexistent-compiled-dir"), None, tmp_path, None, None,
        )

        assert ctx is not None
        assert ctx.trust_model is not None
        assert ctx.trust_model.multi_tenant is False
        assert ctx.trust_model.network_exposure == "loopback"

    def test_wires_precedent_auto_dismiss_when_project_dir_is_known(self, tmp_path):
        """#1208: with a project dir the context carries the hook that records
        a dismissal for an exact precedent match; without one there is no
        action log to write to, so the hook stays None."""
        with_project = _build_router_context(
            Path("/nonexistent-compiled-dir"), None, None, tmp_path, None,
        )
        without_project = _build_router_context(
            Path("/nonexistent-compiled-dir"), None, None, None, None,
        )
        assert with_project is not None and with_project.on_precedent_match is not None
        assert without_project is not None and without_project.on_precedent_match is None


# ---------------------------------------------------------------------------
# run_api_analysis — appends to file
# ---------------------------------------------------------------------------

class TestRunApiAnalysisAppend:
    def test_appends_to_existing_file(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text('{"req":"existing","t":"violation"}\n')

        config = ApiRunnerConfig(model="m", api_base="http://localhost/v1")
        content = json.dumps({"findings": [
            {"req": "NEW-1", "t": "violation", "file": "a.py", "line": 1,
             "w": "new", "snippet": "x = 1", "reason": "placeholder", "severity": "minor"},
        ]})
        raw_client = MagicMock()
        msg = MagicMock(content=content)
        raw_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg)])

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(prompt="test", jsonl_file=jsonl),
                config=config,
            )

        lines = [ln for ln in jsonl.read_text().strip().split("\n") if ln]
        finding_lines = [json.loads(ln) for ln in lines if "_marker" not in ln]
        assert len(finding_lines) == 2
        assert finding_lines[0]["req"] == "existing"
        assert finding_lines[1]["req"] == "NEW-1"

    def test_router_context_built_when_compiled_dir_provided(self, tmp_path):
        """When a compiled dir is passed, the API runner builds a router
        context for enrichment. Without it, the router falls back to a
        default context (no enrichment) but still writes findings + markers."""
        jsonl = tmp_path / "evidence.jsonl"
        config = ApiRunnerConfig(model="m", api_base="http://localhost/v1")
        content = json.dumps({"findings": [
            {"req": "X-1", "t": "violation", "file": "a.py", "line": 1,
             "w": "test", "snippet": "x = 1", "reason": "placeholder", "severity": "minor"},
        ]})
        raw_client = MagicMock()
        msg = MagicMock(content=content)
        raw_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg)])

        with patch("openai.OpenAI") as mock_oa, \
             patch("quodeq.analysis._api_runner._build_router_context",
                   return_value=None) as mock_ctx:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="test", jsonl_file=jsonl,
                    compiled_dir=tmp_path, dimension="security",
                ),
                config=config,
            )
            mock_ctx.assert_called_once()
            args = mock_ctx.call_args.args
            assert args[0] == tmp_path  # compiled_dir
            assert args[1] == "security"  # dimension


# ---------------------------------------------------------------------------
# Cache root in _api_runner honours QUODEQ_CACHE_ROOT
# ---------------------------------------------------------------------------

class TestApiRunnerCacheRootEnv:
    def test_cache_root_honours_quodeq_cache_root_env(self, tmp_path, monkeypatch):
        """QUODEQ_CACHE_ROOT must move the default cache root.

        This pins the resolver every cache-writer call site goes through;
        it does not call run_api_analysis itself.
        """
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path))
        # default_cache_root() should now return tmp_path / "results"
        from quodeq.analysis.cache.local import default_cache_root
        assert default_cache_root() == tmp_path / "results"
