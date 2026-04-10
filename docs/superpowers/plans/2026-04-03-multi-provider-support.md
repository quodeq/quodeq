# Multi-Provider Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Quodeq model-agnostic with dual-mode execution — CLI tools and direct API via OpenAI SDK.

**Architecture:** Extend the existing subprocess runner with a `type` field in provider config. Add a new API runner using the OpenAI Python SDK that produces the same JSONL evidence. Add model tier resolution (orchestrator/light/medium/high) with backward-compatible defaults.

**Tech Stack:** Python, OpenAI SDK (`openai>=1.0.0`), existing Flask API, React dashboard

**Spec:** `docs/superpowers/specs/2026-04-03-multi-provider-support-design.md`

---

### Task 1: Add `openai` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add openai to dependencies**

In `pyproject.toml`, add `openai` as an optional dependency so it's only required for API mode:

```toml
[project.optional-dependencies]
api = [
    "openai>=1.0.0",
]
```

Also add it to the dev group so tests can use it:

```toml
[dependency-groups]
dev = [
    "pytest==9.0.2",
    "pytest-cov==7.1.0",
    "openai>=1.0.0",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `uv sync --group dev`
Expected: openai installed successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add openai SDK as optional dependency for API mode"
```

---

### Task 2: Extend provider config with `type` field

**Files:**
- Modify: `src/quodeq/data/config/ai_providers.json`
- Modify: `src/quodeq/analysis/_provider_cache.py`
- Test: `tests/analysis/test_provider_cache.py`

- [ ] **Step 1: Write test for provider type parsing**

```python
# tests/analysis/test_provider_cache.py
"""Tests for provider configuration cache and type field."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._provider_cache import _ProviderConfigCache, get_provider_configs


class TestProviderConfigType:
    """Provider configs must include a 'type' field (cli or api)."""

    def test_builtin_providers_have_type(self):
        configs = get_provider_configs()
        for name, cfg in configs.items():
            assert "type" in cfg, f"Provider '{name}' missing 'type' field"
            assert cfg["type"] in ("cli", "api"), f"Provider '{name}' has invalid type: {cfg['type']}"

    def test_claude_is_cli_type(self):
        configs = get_provider_configs()
        assert configs["claude"]["type"] == "cli"

    def test_ollama_is_api_type(self):
        configs = get_provider_configs()
        assert configs["ollama"]["type"] == "api"
        assert configs["ollama"]["api_base"] == "http://localhost:11434/v1"

    def test_openrouter_is_api_type(self):
        configs = get_provider_configs()
        assert configs["openrouter"]["type"] == "api"
        assert configs["openrouter"]["api_key_env"] == "OPENROUTER_API_KEY"

    def test_custom_provider_has_env_interpolation_fields(self):
        configs = get_provider_configs()
        assert configs["custom"]["type"] == "api"
        assert "${AI_MODEL}" in configs["custom"]["model"]

    def test_cache_loads_from_file(self, tmp_path):
        cfg_file = tmp_path / "providers.json"
        cfg_file.write_text(json.dumps({
            "test-cli": {"type": "cli", "cmd": "test", "base_args": "--print"},
            "test-api": {"type": "api", "model": "gpt-4o", "api_base": "http://localhost:8000/v1"},
        }))
        cache = _ProviderConfigCache()
        with patch("quodeq.analysis._provider_cache._AI_PROVIDERS_PATH", cfg_file):
            result = cache.get()
        assert result["test-cli"]["type"] == "cli"
        assert result["test-api"]["type"] == "api"

    def test_fallback_configs_have_type(self):
        """Fallback configs used when JSON is unreadable must also have type."""
        cache = _ProviderConfigCache()
        with patch("quodeq.analysis._provider_cache._AI_PROVIDERS_PATH", Path("/nonexistent")):
            result = cache.get()
        for name, cfg in result.items():
            assert "type" in cfg, f"Fallback provider '{name}' missing 'type'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/analysis/test_provider_cache.py -v`
Expected: FAIL — providers missing `type` field

- [ ] **Step 3: Update ai_providers.json**

Replace `src/quodeq/data/config/ai_providers.json` with:

```json
{
  "claude": {
    "type": "cli",
    "cmd": "claude",
    "base_args": "--print --output-format stream-json --verbose",
    "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
    "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
    "env_remove": ["CLAUDECODE"]
  },
  "codex": {
    "type": "cli",
    "cmd": "codex",
    "base_args": "--print --output-format stream-json --verbose",
    "mcp_permission_args": [],
    "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
    "env_remove": []
  },
  "ollama": {
    "type": "api",
    "model": "llama3.1",
    "api_base": "http://localhost:11434/v1"
  },
  "openrouter": {
    "type": "api",
    "model": "anthropic/claude-sonnet-4",
    "api_key_env": "OPENROUTER_API_KEY"
  },
  "custom": {
    "type": "api",
    "model": "${AI_MODEL}",
    "api_base": "${AI_API_BASE}",
    "api_key_env": "AI_API_KEY"
  }
}
```

- [ ] **Step 4: Update fallback configs in _provider_cache.py**

In `src/quodeq/analysis/_provider_cache.py`, update `_PROVIDER_CONFIGS_FALLBACK` to include the `type` field:

```python
_PROVIDER_CONFIGS_FALLBACK: dict[str, dict] = {
    "claude": {
        "type": "cli",
        "cmd": "claude",
        "base_args": "--print --output-format stream-json --verbose",
        "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": ["CLAUDECODE"],
    },
    "codex": {
        "type": "cli",
        "cmd": "codex",
        "base_args": "--print --output-format stream-json --verbose",
        "mcp_permission_args": [],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": [],
    },
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/analysis/test_provider_cache.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/data/config/ai_providers.json src/quodeq/analysis/_provider_cache.py tests/analysis/test_provider_cache.py
git commit -m "feat: add provider type field and API provider entries (ollama, openrouter, custom)"
```

---

### Task 3: Add model tier resolution

**Files:**
- Create: `src/quodeq/config/ai_models.py`
- Test: `tests/config/test_ai_models.py`

- [ ] **Step 1: Write tests for model tier resolution**

```python
# tests/config/test_ai_models.py
"""Tests for model tier resolution."""
from __future__ import annotations

import pytest

from quodeq.config.ai_models import get_model_for_tier, ModelTier


class TestModelTier:
    """Model tier enum values."""

    def test_tier_values(self):
        assert ModelTier.ORCHESTRATOR == "orchestrator"
        assert ModelTier.LIGHT == "light"
        assert ModelTier.MEDIUM == "medium"
        assert ModelTier.HIGH == "high"


class TestGetModelForTier:
    """get_model_for_tier resolves model name from env vars with fallbacks."""

    def test_ai_model_overrides_all_tiers(self):
        env = {"AI_MODEL": "my-model"}
        assert get_model_for_tier(ModelTier.LIGHT, env=env) == "my-model"
        assert get_model_for_tier(ModelTier.HIGH, env=env) == "my-model"

    def test_tier_specific_env_var(self):
        env = {"QUODEQ_MODEL_MEDIUM": "sonnet", "AI_MODEL": "fallback"}
        assert get_model_for_tier(ModelTier.MEDIUM, env=env) == "sonnet"

    def test_tier_env_takes_precedence_over_ai_model(self):
        env = {"QUODEQ_MODEL_HIGH": "opus", "AI_MODEL": "default"}
        assert get_model_for_tier(ModelTier.HIGH, env=env) == "opus"

    def test_falls_back_to_ai_model(self):
        env = {"AI_MODEL": "my-model"}
        assert get_model_for_tier(ModelTier.ORCHESTRATOR, env=env) == "my-model"

    def test_returns_none_when_nothing_set(self):
        assert get_model_for_tier(ModelTier.MEDIUM, env={}) is None

    def test_empty_tier_var_falls_through(self):
        env = {"QUODEQ_MODEL_LIGHT": "", "AI_MODEL": "fallback"}
        assert get_model_for_tier(ModelTier.LIGHT, env=env) == "fallback"

    def test_provider_default_used_as_last_resort(self):
        env = {}
        result = get_model_for_tier(ModelTier.MEDIUM, env=env, provider_default="llama3.1")
        assert result == "llama3.1"

    def test_ai_model_overrides_provider_default(self):
        env = {"AI_MODEL": "custom-model"}
        result = get_model_for_tier(ModelTier.MEDIUM, env=env, provider_default="llama3.1")
        assert result == "custom-model"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/config/test_ai_models.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement model tier resolution**

```python
# src/quodeq/config/ai_models.py
"""Model tier resolution -- maps tier names to concrete model IDs."""
from __future__ import annotations

import os
from enum import StrEnum


class ModelTier(StrEnum):
    """Analysis model tiers, from lightest to heaviest."""

    ORCHESTRATOR = "orchestrator"
    LIGHT = "light"
    MEDIUM = "medium"
    HIGH = "high"


_TIER_ENV_VARS: dict[ModelTier, str] = {
    ModelTier.ORCHESTRATOR: "QUODEQ_MODEL_ORCHESTRATOR",
    ModelTier.LIGHT: "QUODEQ_MODEL_LIGHT",
    ModelTier.MEDIUM: "QUODEQ_MODEL_MEDIUM",
    ModelTier.HIGH: "QUODEQ_MODEL_HIGH",
}


def get_model_for_tier(
    tier: ModelTier,
    *,
    env: dict[str, str] | None = None,
    provider_default: str | None = None,
) -> str | None:
    """Resolve the model name for a given tier.

    Priority: QUODEQ_MODEL_<TIER> > AI_MODEL > provider_default > None
    """
    environ = env if env is not None else os.environ
    tier_var = _TIER_ENV_VARS[tier]
    tier_value = environ.get(tier_var, "").strip()
    if tier_value:
        return tier_value
    ai_model = environ.get("AI_MODEL", "").strip()
    if ai_model:
        return ai_model
    return provider_default
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_ai_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/config/ai_models.py tests/config/test_ai_models.py
git commit -m "feat: add model tier resolution (orchestrator/light/medium/high)"
```

---

### Task 4: Implement the API prompt assembler

**Files:**
- Create: `src/quodeq/analysis/_api_prompt.py`
- Test: `tests/analysis/test_api_prompt.py`

- [ ] **Step 1: Write tests for prompt assembly**

```python
# tests/analysis/test_api_prompt.py
"""Tests for API runner prompt assembly."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis._api_prompt import assemble_api_prompt


@pytest.fixture()
def src_dir(tmp_path):
    """Create a minimal source directory with two files."""
    (tmp_path / "main.py").write_text("def hello():\n    print('hi')\n")
    (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    return tmp_path


@pytest.fixture()
def standards_text():
    return "M-MOD-1: Modules should have a single responsibility.\nS-CON-3: No hardcoded secrets."


class TestAssembleApiPrompt:
    """assemble_api_prompt bundles code + standards into a structured prompt."""

    def test_includes_source_files(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py", src_dir / "utils.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert "main.py" in prompt
        assert "def hello():" in prompt
        assert "utils.py" in prompt
        assert "def add(a, b):" in prompt

    def test_includes_standards(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="security",
            repo_name="test-repo",
        )
        assert "M-MOD-1" in prompt
        assert "S-CON-3" in prompt

    def test_includes_dimension(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="security",
            repo_name="test-repo",
        )
        assert "security" in prompt.lower()

    def test_includes_json_schema(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert '"req"' in prompt
        assert '"severity"' in prompt
        assert '"violation"' in prompt

    def test_handles_unreadable_file_gracefully(self, src_dir, standards_text):
        missing = src_dir / "gone.py"
        prompt = assemble_api_prompt(
            source_files=[missing, src_dir / "main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert "def hello():" in prompt

    def test_returns_string(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/test_api_prompt.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement the prompt assembler**

```python
# src/quodeq/analysis/_api_prompt.py
"""Prompt assembly for the direct API runner.

Bundles source files, standards, and evaluation instructions into a single
prompt that requests structured JSON output matching the JSONL evidence schema.
"""
from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_FINDING_SCHEMA = """\
Each finding must be a JSON object with these fields:
  Required:
    "req": string - requirement ID (e.g. "M-MOD-1", "S-CON-3")
    "t": string - "violation" or "compliance"
    "file": string - file path relative to repo root
    "line": integer - line number
    "severity": string - "critical", "major", or "minor"
    "w": string - short title of the finding
    "reason": string - why this is a violation or compliance
  Optional:
    "end_line": integer - last line if multi-line
    "snippet": string - code snippet
    "scope": string - "file", "class", or "module"
"""

_SYSTEM_TEMPLATE = """\
You are a code quality evaluator. Analyze the provided source code against \
the given standards for the "{dimension}" dimension.

Repository: {repo_name}

## Standards

{standards_text}

## Output Format

Return a JSON object with a single key "findings" containing an array of finding objects.

{schema}

Example:
{{"findings": [{{"req": "M-MOD-1", "t": "violation", "file": "src/app.py", "line": 10, \
"severity": "major", "w": "Multiple responsibilities", "reason": "Module handles both IO and logic"}}]}}

If no findings, return: {{"findings": []}}

## Source Files

{files_block}

Analyze these files for the "{dimension}" dimension only. \
Report violations and notable compliance. Be precise with line numbers.
"""


def _read_file_safe(path: Path) -> str | None:
    """Read a file, returning None on failure."""
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        _log.warning("Could not read file: %s", path)
        return None


def _build_files_block(source_files: list[Path]) -> str:
    """Build the source files block for the prompt."""
    parts: list[str] = []
    for path in source_files:
        content = _read_file_safe(path)
        if content is None:
            continue
        parts.append(f"### {path.name}\n```\n{content}\n```")
    return "\n\n".join(parts)


def assemble_api_prompt(
    *,
    source_files: list[Path],
    standards_text: str,
    dimension: str,
    repo_name: str,
) -> str:
    """Assemble a complete evaluation prompt for the API runner."""
    files_block = _build_files_block(source_files)
    return _SYSTEM_TEMPLATE.format(
        dimension=dimension,
        repo_name=repo_name,
        standards_text=standards_text,
        schema=_FINDING_SCHEMA,
        files_block=files_block,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/analysis/test_api_prompt.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/_api_prompt.py tests/analysis/test_api_prompt.py
git commit -m "feat: add API prompt assembler for direct LLM evaluation"
```

---

### Task 5: Implement the API runner

**Files:**
- Create: `src/quodeq/analysis/_api_runner.py`
- Test: `tests/analysis/test_api_runner.py`

- [ ] **Step 1: Write tests for the API runner**

```python
# tests/analysis/test_api_runner.py
"""Tests for the OpenAI SDK-based API runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._api_runner import run_api_analysis, ApiRunnerConfig


@pytest.fixture()
def mock_openai_response():
    """Create a mock OpenAI chat completion response."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "findings": [
            {
                "req": "M-MOD-1",
                "t": "violation",
                "file": "main.py",
                "line": 5,
                "severity": "major",
                "w": "Multiple responsibilities",
                "reason": "Module mixes IO and business logic",
            },
            {
                "req": "S-CON-3",
                "t": "compliance",
                "file": "utils.py",
                "line": 1,
                "severity": "minor",
                "w": "No hardcoded secrets",
                "reason": "No secrets found in file",
            },
        ]
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@pytest.fixture()
def api_config():
    """Create a minimal ApiRunnerConfig."""
    return ApiRunnerConfig(
        model="test-model",
        api_base="http://localhost:11434/v1",
        api_key="test-key",
    )


class TestRunApiAnalysis:
    """run_api_analysis calls OpenAI SDK and writes JSONL evidence."""

    def test_writes_jsonl_findings(self, tmp_path, mock_openai_response, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        (tmp_path / "main.py").write_text("x = 1\n")

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 2
        finding = json.loads(lines[0])
        assert finding["req"] == "M-MOD-1"
        assert finding["t"] == "violation"

    def test_passes_model_and_base_url(self, tmp_path, mock_openai_response, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

            mock_openai.OpenAI.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="test-key",
            )
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "test-model"

    def test_handles_empty_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({"findings": []})
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

        assert jsonl_file.exists()
        assert jsonl_file.read_text().strip() == ""

    def test_handles_malformed_json_response(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        mock_choice = MagicMock()
        mock_choice.message.content = "This is not JSON at all"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            with pytest.raises(ValueError, match="parse"):
                run_api_analysis(
                    prompt="test prompt",
                    jsonl_file=jsonl_file,
                    config=api_config,
                )

    def test_requests_json_response_format(self, tmp_path, mock_openai_response, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/test_api_runner.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement the API runner**

```python
# src/quodeq/analysis/_api_runner.py
"""OpenAI SDK-based API runner for direct LLM evaluation.

Calls any OpenAI-compatible API (Ollama, OpenRouter, LM Studio, etc.)
and writes findings as JSONL evidence -- the same format the CLI runner
produces via MCP.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiRunnerConfig:
    """Configuration for a single API runner invocation."""

    model: str
    api_base: str
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int | None = None


def _parse_findings(raw: str) -> list[dict]:
    """Parse the LLM response into a list of finding dicts.

    Raises ValueError if the response is not valid JSON with a 'findings' key.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse LLM response as JSON: {exc}") from exc

    if isinstance(data, dict) and "findings" in data:
        findings = data["findings"]
        if isinstance(findings, list):
            return findings

    raise ValueError(
        "LLM response missing 'findings' array. "
        f"Got keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
    )


def run_api_analysis(
    *,
    prompt: str,
    jsonl_file: Path,
    config: ApiRunnerConfig,
) -> None:
    """Call an OpenAI-compatible API and write findings to JSONL.

    Raises ImportError if the openai package is not installed.
    Raises ValueError if the LLM response cannot be parsed.
    """
    if openai is None:
        raise ImportError(
            "The 'openai' package is required for API mode. "
            "Install it with: pip install 'quodeq[api]'"
        )

    client = openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key,
    )

    create_kwargs: dict = dict(
        model=config.model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=config.temperature,
    )
    if config.max_tokens is not None:
        create_kwargs["max_tokens"] = config.max_tokens

    _log.info("Calling %s model=%s", config.api_base, config.model)
    response = client.chat.completions.create(**create_kwargs)

    raw_content = response.choices[0].message.content
    findings = _parse_findings(raw_content)

    _log.info("Received %d findings from API", len(findings))

    with open(jsonl_file, "w") as fh:
        for finding in findings:
            fh.write(json.dumps(finding) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/analysis/test_api_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/_api_runner.py tests/analysis/test_api_runner.py
git commit -m "feat: add OpenAI SDK-based API runner for direct LLM evaluation"
```

---

### Task 6: Add provider type routing in the analysis dispatcher

**Files:**
- Modify: `src/quodeq/analysis/subprocess.py`
- Test: `tests/analysis/test_runner_dispatch.py`

- [ ] **Step 1: Write tests for provider type routing**

```python
# tests/analysis/test_runner_dispatch.py
"""Tests for runner dispatch based on provider type."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subprocess import run_analysis
from quodeq.analysis._config import AnalysisConfig


class TestRunnerDispatch:
    """run_analysis routes to CLI or API runner based on provider config type."""

    def test_cli_type_uses_subprocess(self, tmp_path):
        """Provider with type=cli should call the subprocess runner."""
        stream_file = tmp_path / "stream.json"
        stream_file.touch()
        cfg = AnalysisConfig(ai_cmd="claude")

        with patch("quodeq.analysis.subprocess._run_cli_analysis") as mock_cli:
            mock_cli.return_value = None
            run_analysis(
                work_dir=tmp_path, prompt="test", stream_file=stream_file, config=cfg,
            )
            mock_cli.assert_called_once()

    def test_api_type_uses_api_runner(self, tmp_path):
        """Provider with type=api should call the API runner."""
        stream_file = tmp_path / "stream.json"
        stream_file.touch()
        jsonl_file = tmp_path / "evidence.jsonl"
        cfg = AnalysisConfig(ai_cmd="ollama", jsonl_file=jsonl_file)

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis.subprocess._run_api_analysis_bridge") as mock_api:
            mock_cfg.return_value = {
                "ollama": {
                    "type": "api",
                    "model": "llama3.1",
                    "api_base": "http://localhost:11434/v1",
                }
            }
            mock_api.return_value = None
            run_analysis(
                work_dir=tmp_path, prompt="test", stream_file=stream_file, config=cfg,
            )
            mock_api.assert_called_once()

    def test_unknown_provider_defaults_to_cli(self, tmp_path):
        """Unknown providers should fall back to CLI runner."""
        stream_file = tmp_path / "stream.json"
        stream_file.touch()
        cfg = AnalysisConfig(ai_cmd="unknown-tool")

        with patch("quodeq.analysis.subprocess._run_cli_analysis") as mock_cli:
            mock_cli.return_value = None
            run_analysis(
                work_dir=tmp_path, prompt="test", stream_file=stream_file, config=cfg,
            )
            mock_cli.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/test_runner_dispatch.py -v`
Expected: FAIL — `_run_cli_analysis` not found

- [ ] **Step 3: Refactor subprocess.py to support dual dispatch**

Replace `src/quodeq/analysis/subprocess.py` with:

```python
"""AI analysis runner -- dispatches to CLI subprocess or API runner.

This module is the public entry point. Implementation is split across:
- _config.py:      AnalysisConfig, HeartbeatCallback, dataclasses
- _mcp_config.py:  MCP config file creation
- _command.py:     CLI argument and environment construction
- _process.py:     Process spawning, heartbeat, error handling
- _api_runner.py:  OpenAI SDK-based direct API runner
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from quodeq.analysis._command import _build_ai_cmd, _build_analysis_env
from quodeq.analysis._config import AnalysisConfig, HeartbeatCallback, _SpawnPaths
from quodeq.analysis._process import AnalysisError, _check_process_result, _spawn_and_monitor
from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.shared.utils import get_ai_cmd

_log = logging.getLogger(__name__)

# Re-export public API so existing imports keep working
__all__ = [
    "AnalysisConfig",
    "AnalysisError",
    "HeartbeatCallback",
    "count_files_from_stream",
    "run_analysis",
    "_build_ai_cmd",
]


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(count_files_in_stream(stream_file))


def _get_provider_type(ai_cmd: str) -> str:
    """Determine the provider type (cli or api) from the provider config."""
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})
    return provider_cfg.get("type", "cli")


def _run_cli_analysis(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via CLI subprocess (existing behavior)."""
    args, mcp_config_path = _build_ai_cmd(prompt, cfg, work_dir=work_dir)
    env = _build_analysis_env(cfg.ai_cmd or get_ai_cmd())
    stream_err = Path(str(stream_file) + ".err")

    try:
        process, timed_out = _spawn_and_monitor(
            args, work_dir, env, _SpawnPaths(stream_file, stream_err), cfg,
        )
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)

    if not timed_out:
        _check_process_result(process, stream_err)


def _run_api_analysis_bridge(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via direct API call (new behavior)."""
    from quodeq.analysis._api_runner import run_api_analysis, ApiRunnerConfig

    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})

    model = cfg.ai_model or provider_cfg.get("model", "")
    api_base = provider_cfg.get("api_base", "")
    api_key_env = provider_cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""

    if not model:
        raise AnalysisError(f"No model configured for API provider '{ai_cmd}'")
    if not api_base:
        raise AnalysisError(f"No api_base configured for API provider '{ai_cmd}'")

    jsonl_file = cfg.jsonl_file
    if jsonl_file is None:
        jsonl_file = Path(str(stream_file).replace(".stream", "_evidence.jsonl"))

    run_api_analysis(
        prompt=prompt,
        jsonl_file=jsonl_file,
        config=ApiRunnerConfig(
            model=model,
            api_base=api_base,
            api_key=api_key,
        ),
    )

    # Write a minimal stream file so downstream checks (is_stream_valid) pass
    stream_file.write_text('{"type":"api_runner","status":"complete"}\n')
    _log.info("API analysis complete, evidence written to %s", jsonl_file)


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
) -> None:
    """Run AI analysis, dispatching to CLI or API runner based on provider type."""
    cfg = config or AnalysisConfig()
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    provider_type = _get_provider_type(ai_cmd)

    if provider_type == "api":
        _run_api_analysis_bridge(work_dir, prompt, stream_file, cfg)
    else:
        _run_cli_analysis(work_dir, prompt, stream_file, cfg)
```

- [ ] **Step 4: Run dispatch tests to verify they pass**

Run: `uv run pytest tests/analysis/test_runner_dispatch.py -v`
Expected: All PASS

- [ ] **Step 5: Run existing analysis tests to verify no regressions**

Run: `uv run pytest tests/analysis/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/analysis/subprocess.py tests/analysis/test_runner_dispatch.py
git commit -m "feat: add dual dispatch — route to CLI or API runner based on provider type"
```

---

### Task 7: Expand provider configuration (ai_provider.py)

**Files:**
- Modify: `src/quodeq/config/ai_provider.py`
- Modify: `tests/config/test_config_ai_provider.py`

- [ ] **Step 1: Write tests for expanded providers**

Add the following test class to `tests/config/test_config_ai_provider.py`:

```python
class TestExpandedProviders:
    """PROVIDERS dict should include API-mode providers."""

    def test_ollama_in_providers(self):
        from quodeq.config.ai_provider import PROVIDERS
        assert "ollama" in PROVIDERS

    def test_openrouter_in_providers(self):
        from quodeq.config.ai_provider import PROVIDERS
        assert "openrouter" in PROVIDERS

    def test_custom_in_providers(self):
        from quodeq.config.ai_provider import PROVIDERS
        assert "custom" in PROVIDERS

    def test_ollama_no_api_key_required(self):
        from quodeq.config.ai_provider import PROVIDERS
        api_key_var, cmd = PROVIDERS["ollama"]
        assert api_key_var == ""

    def test_openrouter_api_key_env(self):
        from quodeq.config.ai_provider import PROVIDERS
        api_key_var, cmd = PROVIDERS["openrouter"]
        assert api_key_var == "OPENROUTER_API_KEY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/config/test_config_ai_provider.py::TestExpandedProviders -v`
Expected: FAIL — "ollama" not in PROVIDERS

- [ ] **Step 3: Expand the PROVIDERS dict**

In `src/quodeq/config/ai_provider.py`, update:

```python
PROVIDERS = {
    "claude": ("ANTHROPIC_API_KEY", "claude"),
    "copilot": ("GITHUB_TOKEN", "copilot"),
    "codex": ("CODEX_API_KEY", "codex"),
    "ollama": ("", "ollama"),
    "openrouter": ("OPENROUTER_API_KEY", "openrouter"),
    "custom": ("AI_API_KEY", "custom"),
}
```

Also update the error message in `configure_provider_noninteractive`:

```python
    if provider not in PROVIDERS:
        valid = ", ".join(sorted(PROVIDERS.keys()))
        log_error(f"Invalid provider: {provider}. Expected one of: {valid}")
        return 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_config_ai_provider.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/config/ai_provider.py tests/config/test_config_ai_provider.py
git commit -m "feat: expand PROVIDERS with ollama, openrouter, and custom API entries"
```

---

### Task 8: Update dashboard client discovery for API providers

**Files:**
- Modify: `src/quodeq/services/tooling_mixin.py`
- Test: `tests/services/test_tooling_api_clients.py`

- [ ] **Step 1: Write tests for API provider discovery**

```python
# tests/services/test_tooling_api_clients.py
"""Tests for API provider discovery in tooling mixin."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.services.tooling_mixin import FsToolingMixin


class TestGetAiClientsIncludesApiProviders:
    """get_ai_clients should include API providers alongside CLI tools."""

    def test_includes_api_providers_from_config(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"},
                "openrouter": {"type": "api", "model": "claude-sonnet-4", "api_key_env": "OPENROUTER_API_KEY"},
                "claude": {"type": "cli", "cmd": "claude"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        client_ids = [c["id"] for c in result["clients"]]
        assert "ollama" in client_ids
        assert "openrouter" in client_ids

    def test_api_providers_have_type_label(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        ollama = [c for c in result["clients"] if c["id"] == "ollama"][0]
        assert ollama["type"] == "api"

    def test_cli_providers_still_require_which(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "claude": {"type": "cli", "cmd": "claude"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        client_ids = [c["id"] for c in result["clients"]]
        assert "claude" not in client_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/services/test_tooling_api_clients.py -v`
Expected: FAIL — `get_provider_configs` not imported in tooling_mixin

- [ ] **Step 3: Update get_ai_clients to include API providers**

In `src/quodeq/services/tooling_mixin.py`, add this import near the top:

```python
from quodeq.analysis._provider_cache import get_provider_configs
```

Then replace the `get_ai_clients` method:

```python
    def get_ai_clients(self, env: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
        """Return available AI clients (CLI tools that are installed + API providers).

        *env* overrides ``os.environ`` when provided, making the method
        testable without environment mutation.
        """
        environ = env if env is not None else os.environ
        clients: list[dict[str, str]] = []

        # CLI tools: only include if installed
        if "QUODEQ_AI_CLIENTS" in environ:
            ids = [c.strip() for c in environ["QUODEQ_AI_CLIENTS"].split(",") if c.strip()]
            candidates = [{"id": c, "label": c.capitalize()} for c in ids]
        else:
            candidates = self._CLI_CANDIDATES

        for c in candidates:
            if shutil.which(c["id"]):
                clients.append({**c, "type": "cli"})

        # API providers: always available (no CLI binary needed)
        provider_configs = get_provider_configs()
        for provider_id, cfg in provider_configs.items():
            if cfg.get("type") == "api" and provider_id != "custom":
                if not any(c["id"] == provider_id for c in clients):
                    clients.append({
                        "id": provider_id,
                        "label": provider_id.capitalize(),
                        "type": "api",
                    })

        return {"clients": clients}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_tooling_api_clients.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/services/tooling_mixin.py tests/services/test_tooling_api_clients.py
git commit -m "feat: include API providers in client discovery for dashboard"
```

---

### Task 9: Update dashboard UI for provider types

**Files:**
- Modify: `src/quodeq/ui/src/features/settings/components/ModelSection.jsx`

- [ ] **Step 1: Update ClientSelector to show both CLI and API providers**

In `src/quodeq/ui/src/features/settings/components/ModelSection.jsx`, replace the `ClientSelector` function:

```jsx
function ClientSelector({ aiCmd, availableClients }) {
  const { value, onApply } = aiCmd;
  if (availableClients === null) {
    return (
      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">Client</span>
          <span className="settings-description">Detecting...</span>
        </div>
      </div>
    );
  }

  const cliClients = availableClients.filter((c) => c.type === 'cli' || !c.type);
  const apiClients = availableClients.filter((c) => c.type === 'api');

  return (
    <>
      <div className={`settings-row${!value && apiClients.length === 0 ? ' settings-row--last' : ''}`}>
        <div className="settings-row-label">
          <span className="settings-label">Client</span>
          <span className="settings-description">CLI tool or API provider for analysis</span>
        </div>
        <div className="theme-toggle">
          {cliClients.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={`theme-toggle-btn${value === id ? ' active' : ''}`}
              onClick={() => onApply(id)}
            >
              {label}
            </button>
          ))}
          {apiClients.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={`theme-toggle-btn${value === id ? ' active' : ''}`}
              onClick={() => onApply(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {cliClients.length === 0 && apiClients.length === 0 && (
        <div className="settings-row settings-row--last settings-install-guide">
          <div className="settings-row-label">
            <span className="settings-label">No providers detected</span>
            <span className="settings-description">
              Install a CLI tool or configure an API provider.
            </span>
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Build the UI**

Run: `cd ui/web && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Copy built assets to static directory**

Run: `cp -r ui/web/dist/* src/quodeq/static/`
Expected: Static files updated

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/features/settings/components/ModelSection.jsx src/quodeq/static/
git commit -m "feat(ui): update settings to show CLI and API providers"
```

---

### Task 10: Integration test — end-to-end API runner flow

**Files:**
- Create: `tests/analysis/test_api_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/analysis/test_api_integration.py
"""Integration test: full API runner flow from provider config to JSONL evidence."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subprocess import run_analysis
from quodeq.analysis._config import AnalysisConfig


@pytest.fixture()
def source_repo(tmp_path):
    """Create a minimal source repo for evaluation."""
    src = tmp_path / "repo"
    src.mkdir()
    (src / "main.py").write_text(
        "import os\n"
        "password = 'hunter2'\n"
        "def run():\n"
        "    os.system(password)\n"
    )
    return src


class TestApiIntegration:
    """End-to-end: run_analysis with API provider produces JSONL evidence."""

    def test_full_flow(self, source_repo, tmp_path):
        stream_file = tmp_path / "stream.json"
        jsonl_file = tmp_path / "evidence.jsonl"

        mock_findings = {
            "findings": [
                {
                    "req": "S-CON-3",
                    "t": "violation",
                    "file": "main.py",
                    "line": 2,
                    "severity": "critical",
                    "w": "Hardcoded password",
                    "reason": "Password stored as plaintext string literal",
                },
            ]
        }

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(mock_findings)
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis._api_runner.openai") as mock_openai:

            mock_cfg.return_value = {
                "ollama": {
                    "type": "api",
                    "model": "llama3.1",
                    "api_base": "http://localhost:11434/v1",
                }
            }

            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            cfg = AnalysisConfig(ai_cmd="ollama", jsonl_file=jsonl_file)
            run_analysis(
                work_dir=source_repo,
                prompt="Evaluate this code for security issues.",
                stream_file=stream_file,
                config=cfg,
            )

        # Verify JSONL evidence was produced
        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 1
        finding = json.loads(lines[0])
        assert finding["req"] == "S-CON-3"
        assert finding["t"] == "violation"
        assert finding["severity"] == "critical"

        # Verify stream file was created (for downstream checks)
        assert stream_file.exists()
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/analysis/test_api_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/analysis/test_api_integration.py
git commit -m "test: add end-to-end integration test for API runner flow"
```

---

### Task 11: Final verification and cleanup

- [ ] **Step 1: Run full test suite with coverage**

Run: `uv run pytest tests/ -v --cov=quodeq --cov-report=term-missing --timeout=60`
Expected: All PASS, coverage at or above 60%

- [ ] **Step 2: Verify backward compatibility**

Run: `uv run python -c "from quodeq.analysis.subprocess import run_analysis; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Verify openai import is lazy**

Run: `uv run python -c "from quodeq.analysis.subprocess import run_analysis; print('No openai import at module level')"`
Expected: Works even if openai is not installed (import is lazy in `_api_runner.py`)

- [ ] **Step 4: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final cleanup for multi-provider support (Phase 1)"
```
