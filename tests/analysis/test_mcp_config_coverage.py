"""Tests for analysis._mcp_config — MCP server config file generation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from quodeq.analysis._config import _AgentParams
from quodeq.analysis._mcp_config import _create_mcp_config


class TestCreateMcpConfig:
    def test_basic_config(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        config_path = _create_mcp_config(jsonl)
        try:
            assert config_path.exists()
            data = json.loads(config_path.read_text())
            assert "mcpServers" in data
            assert "findings" in data["mcpServers"]
            server = data["mcpServers"]["findings"]
            assert "command" in server
            assert str(jsonl.resolve()) in server["args"]
        finally:
            config_path.unlink(missing_ok=True)

    def test_with_compiled_dir_and_dimension(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        config_path = _create_mcp_config(jsonl, compiled_dir=compiled, dimension="security")
        try:
            data = json.loads(config_path.read_text())
            args = data["mcpServers"]["findings"]["args"]
            assert "--compiled-dir" in args
            assert str(compiled.resolve()) in args
            assert "--dimension" in args
            assert "security" in args
        finally:
            config_path.unlink(missing_ok=True)

    def test_compiled_dir_without_dimension_omitted(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        # compiled_dir set but dimension is None => should NOT add --compiled-dir
        config_path = _create_mcp_config(jsonl, compiled_dir=compiled, dimension=None)
        try:
            data = json.loads(config_path.read_text())
            args = data["mcpServers"]["findings"]["args"]
            assert "--compiled-dir" not in args
        finally:
            config_path.unlink(missing_ok=True)

    def test_with_agent_params(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        queue = tmp_path / "queue.json"
        queue.touch()
        work = tmp_path / "work"
        work.mkdir()
        params = _AgentParams(queue_path=queue, agent_id="agent-1", work_dir=work)
        config_path = _create_mcp_config(jsonl, agent_params=params)
        try:
            data = json.loads(config_path.read_text())
            args = data["mcpServers"]["findings"]["args"]
            assert "--queue" in args
            assert str(queue.resolve()) in args
            assert "--agent-id" in args
            assert "agent-1" in args
            assert "--work-dir" in args
            assert str(work.resolve()) in args
        finally:
            config_path.unlink(missing_ok=True)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX permission bits don't apply on Windows file mode",
    )
    def test_file_permissions(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        config_path = _create_mcp_config(jsonl)
        try:
            stat = os.stat(config_path)
            assert stat.st_mode & 0o777 == 0o600
        finally:
            config_path.unlink(missing_ok=True)

    def test_no_agent_params_defaults(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        config_path = _create_mcp_config(jsonl, agent_params=None)
        try:
            data = json.loads(config_path.read_text())
            args = data["mcpServers"]["findings"]["args"]
            assert "--queue" not in args
            assert "--agent-id" not in args
            assert "--work-dir" not in args
        finally:
            config_path.unlink(missing_ok=True)

    def test_includes_cache_root_model_id_language(self, tmp_path):
        """Task 3.5 #6: the JSON config file's args list MUST include
        --cache-root, --model-id, and --language so the subprocess can build
        a cache writer whose fingerprint matches classify_files_via_cache.
        """
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        params = _AgentParams(model_id="sonnet", language="kotlin")
        config_path = _create_mcp_config(jsonl, agent_params=params)
        try:
            data = json.loads(config_path.read_text())
            args = data["mcpServers"]["findings"]["args"]
            assert "--cache-root" in args
            assert "--model-id" in args
            assert "--language" in args
            model_idx = args.index("--model-id")
            assert args[model_idx + 1] == "sonnet"
            lang_idx = args.index("--language")
            assert args[lang_idx + 1] == "kotlin"
            cr_idx = args.index("--cache-root")
            assert args[cr_idx + 1].endswith(".quodeq/cache/results")
        finally:
            config_path.unlink(missing_ok=True)

    def test_cache_flag_fallbacks(self, tmp_path):
        """No _AgentParams overrides => model_id='unknown', language=''."""
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        config_path = _create_mcp_config(jsonl, agent_params=None)
        try:
            data = json.loads(config_path.read_text())
            args = data["mcpServers"]["findings"]["args"]
            assert "--cache-root" in args
            model_idx = args.index("--model-id")
            assert args[model_idx + 1] == "unknown"
            lang_idx = args.index("--language")
            assert args[lang_idx + 1] == ""
        finally:
            config_path.unlink(missing_ok=True)
