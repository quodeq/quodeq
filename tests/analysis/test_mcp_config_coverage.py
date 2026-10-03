"""Tests for analysis._mcp_config — MCP server config file generation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from quodeq.analysis._config import AgentParams
from quodeq.analysis._mcp_config import create_mcp_config


@pytest.fixture
def findings_jsonl(tmp_path: Path) -> Path:
    """An empty ``findings.jsonl`` for the generated config to point at."""
    jsonl = tmp_path / "findings.jsonl"
    jsonl.touch()
    return jsonl


@pytest.fixture
def make_mcp_config(findings_jsonl: Path):
    """Build an MCP config file and delete every file built, pass or fail.

    ``create_mcp_config`` writes outside tmp_path, so the cleanup has to be
    explicit; a fixture does it once instead of a try/finally per test.
    """
    created: list[Path] = []

    def build(jsonl: Path | None = None, **kwargs) -> Path:
        path = create_mcp_config(jsonl or findings_jsonl, **kwargs)
        created.append(path)
        return path

    yield build
    for path in created:
        path.unlink(missing_ok=True)


class TestCreateMcpConfig:
    def test_basic_config(self, findings_jsonl, make_mcp_config):
        config_path = make_mcp_config()
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert "mcpServers" in data
        assert "findings" in data["mcpServers"]
        server = data["mcpServers"]["findings"]
        assert "command" in server
        assert str(findings_jsonl.resolve()) in server["args"]

    def test_with_compiled_dir_and_dimension(self, tmp_path, make_mcp_config):
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        config_path = make_mcp_config(compiled_dir=compiled, dimension="security")
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--compiled-dir" in args
        assert str(compiled.resolve()) in args
        assert "--dimension" in args
        assert "security" in args

    def test_compiled_dir_without_dimension_omitted(self, tmp_path, make_mcp_config):
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        # compiled_dir set but dimension is None => should NOT add --compiled-dir
        config_path = make_mcp_config(compiled_dir=compiled, dimension=None)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--compiled-dir" not in args

    def test_with_agent_params(self, tmp_path, make_mcp_config):
        queue = tmp_path / "queue.json"
        queue.touch()
        work = tmp_path / "work"
        work.mkdir()
        params = AgentParams(queue_path=queue, agent_id="agent-1", work_dir=work)
        config_path = make_mcp_config(agent_params=params)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--queue" in args
        assert str(queue.resolve()) in args
        assert "--agent-id" in args
        assert "agent-1" in args
        assert "--work-dir" in args
        assert str(work.resolve()) in args

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX permission bits don't apply on Windows file mode",
    )
    def test_file_permissions(self, make_mcp_config):
        config_path = make_mcp_config()
        stat = os.stat(config_path)
        assert stat.st_mode & 0o777 == 0o600

    def test_no_agent_params_defaults(self, make_mcp_config):
        config_path = make_mcp_config(agent_params=None)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--queue" not in args
        assert "--agent-id" not in args
        assert "--work-dir" not in args

    def test_includes_cache_root_model_id_language(self, make_mcp_config):
        """#6: the JSON config file's args list MUST include
        --cache-root, --model-id, and --language so the subprocess can build
        a cache writer whose fingerprint matches classify_files_via_cache.
        """
        params = AgentParams(model_id="sonnet", language="kotlin", cache_root=Path("cache") / "results")
        config_path = make_mcp_config(agent_params=params)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--cache-root" in args
        assert "--model-id" in args
        assert "--language" in args
        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "sonnet"
        lang_idx = args.index("--language")
        assert args[lang_idx + 1] == "kotlin"
        # The agent's resolved cache root travels verbatim (run_analysis
        # resolves it from QUODEQ_CACHE_ROOT or the default).
        # Compare via Path so the tail check holds on every OS.
        cr_idx = args.index("--cache-root")
        expected_tail = str(Path("cache") / "results")
        assert args[cr_idx + 1].endswith(expected_tail)

    def test_cache_root_comes_from_agent_params(self, tmp_path, monkeypatch, make_mcp_config):
        """Fix A (#2419): the run's resolved cache root reaches the generated MCP
        config; an exported QUODEQ_CACHE_ROOT is not re-read here."""
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        config_path = make_mcp_config(agent_params=AgentParams(cache_root=tmp_path / "results"))
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        cr_idx = args.index("--cache-root")
        assert Path(args[cr_idx + 1]) == tmp_path / "results"

    def test_includes_standards_dir_from_agent_params(self, tmp_path, make_mcp_config):
        """Final-review fix: --standards-dir is emitted from
        AgentParams.standards_dir -- the standards ROOT, distinct from
        --compiled-dir (already .../compiled). Regression coverage for the
        bug where findings_server.py received compiled_dir where it expected
        the root, doubling the "compiled" path segment and silently missing
        the params fingerprint.
        """
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()
        params = AgentParams(standards_dir=standards_dir)
        config_path = make_mcp_config(agent_params=params)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--standards-dir" in args
        assert str(standards_dir.resolve()) in args

    def test_standards_dir_omitted_by_default(self, make_mcp_config):
        """No AgentParams.standards_dir => --standards-dir is omitted
        entirely (back-compat: cache writer degrades to no params fingerprint,
        not a crash)."""
        config_path = make_mcp_config(agent_params=None)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--standards-dir" not in args

    def test_cache_flag_fallbacks(self, make_mcp_config):
        """No AgentParams overrides => model_id='unknown', language='', no cache root."""
        config_path = make_mcp_config(agent_params=None)
        data = json.loads(config_path.read_text())
        args = data["mcpServers"]["findings"]["args"]
        assert "--cache-root" not in args
        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "unknown"
        lang_idx = args.index("--language")
        assert args[lang_idx + 1] == ""


class TestFindingsServerArgsAreShared:
    """create_mcp_config and codex_mcp_config_arg must emit the same flags.

    They used to hold two copies of the same 14-line block; both now go
    through _findings_server_args.
    """

    @staticmethod
    def _flag_values(args: list[str]) -> dict[str, str]:
        flags = (
            "--compiled-dir", "--dimension", "--standards-dir", "--queue",
            "--agent-id", "--work-dir", "--cache-root", "--model-id", "--language",
        )
        return {a: args[i + 1] for i, a in enumerate(args) if a in flags}

    def _fixture(self, tmp_path, findings_jsonl):
        jsonl = findings_jsonl
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        standards = tmp_path / "standards"
        standards.mkdir()
        queue = tmp_path / "queue.jsonl"
        queue.touch()
        work = tmp_path / "work"
        work.mkdir()
        ap = AgentParams(
            queue_path=queue, agent_id="agent-7", work_dir=work,
            model_id="sonnet", language="python", standards_dir=standards, cache_root=tmp_path / "cache",
        )
        return jsonl, compiled, ap

    def test_both_emitters_agree(self, tmp_path, findings_jsonl, make_mcp_config):
        from quodeq.analysis._mcp_config import codex_mcp_config_arg
        expected_cache_root = str(tmp_path / "cache")

        jsonl, compiled, ap = self._fixture(tmp_path, findings_jsonl)

        config_path = make_mcp_config(
            jsonl, compiled_dir=compiled, dimension="security", agent_params=ap,
        )
        file_args = json.loads(config_path.read_text())["mcpServers"]["findings"]["args"]
        codex = codex_mcp_config_arg(
            jsonl, compiled_dir=compiled, dimension="security", agent_params=ap,
        )

        values = self._flag_values(file_args)
        assert values == {
            "--compiled-dir": str(compiled.resolve()),
            "--dimension": "security",
            "--standards-dir": str((tmp_path / "standards").resolve()),
            "--queue": str((tmp_path / "queue.jsonl").resolve()),
            "--agent-id": "agent-7",
            "--work-dir": str((tmp_path / "work").resolve()),
            "--cache-root": expected_cache_root,
            "--model-id": "sonnet",
            "--language": "python",
        }
        # The codex override is TOML, so paths are emitted through
        # json.dumps and carry escaped backslashes on Windows.
        for flag, value in values.items():
            assert flag in codex
            assert json.dumps(value) in codex

    def test_helper_output_is_the_shared_tail(self, tmp_path, findings_jsonl, make_mcp_config):
        from quodeq.analysis._mcp_config import _findings_server_args

        jsonl, compiled, ap = self._fixture(tmp_path, findings_jsonl)

        tail = _findings_server_args(compiled, "security", ap)

        config_path = make_mcp_config(
            jsonl, compiled_dir=compiled, dimension="security", agent_params=ap,
        )
        file_args = json.loads(config_path.read_text())["mcpServers"]["findings"]["args"]
        assert file_args[-len(tail):] == tail
        assert file_args[-len(tail) - 1] == str(jsonl.resolve())
