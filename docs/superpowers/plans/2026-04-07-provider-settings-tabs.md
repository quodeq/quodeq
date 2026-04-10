# Provider Settings Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat Analysis settings with tabbed per-provider configuration, backed by a clean `llm_bridge` module that owns all provider interaction.

**Architecture:** Bottom-up build — llm_bridge module first (providers, ollama, cloud, models), then API routes wrapping it, then React UI components. Each tab has independent state keyed by provider ID in localStorage.

**Tech Stack:** Python 3.12+, Flask (direct route registration, no blueprints), React (functional components + hooks), localStorage for persistence, `urllib.request` for Ollama HTTP calls.

---

### Task 1: llm_bridge — Provider Detection

**Files:**
- Create: `src/quodeq/llm_bridge/__init__.py`
- Create: `src/quodeq/llm_bridge/_providers.py`
- Test: `tests/llm_bridge/test_providers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm_bridge/__init__.py
# (empty)
```

```python
# tests/llm_bridge/test_providers.py
"""Tests for llm_bridge provider detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
)


class TestGetProviderConfigs:
    def test_returns_dict(self):
        configs = get_provider_configs()
        assert isinstance(configs, dict)

    def test_contains_known_providers(self):
        configs = get_provider_configs()
        assert "claude" in configs or "ollama" in configs


class TestGetProviderType:
    def test_cli_provider(self):
        assert get_provider_type("claude") == "cli"

    def test_api_provider(self):
        assert get_provider_type("ollama") == "api"

    def test_unknown_defaults_to_cli(self):
        assert get_provider_type("nonexistent-tool") == "cli"


class TestClassifyProvider:
    def test_ollama_is_local_api(self):
        result = classify_provider("ollama")
        assert result == "local-api"

    def test_claude_is_cli(self):
        result = classify_provider("claude")
        assert result == "cli"

    def test_openrouter_is_cloud_api(self):
        result = classify_provider("openrouter")
        assert result == "cloud-api"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm_bridge/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quodeq.llm_bridge'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/quodeq/llm_bridge/__init__.py
"""LLM Bridge — clean interface to LLM providers.

The analysis layer calls this module instead of talking to
Ollama/OpenRouter/CLI tools directly.
"""
from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
)

__all__ = [
    "get_provider_configs",
    "get_provider_type",
    "classify_provider",
]
```

```python
# src/quodeq/llm_bridge/_providers.py
"""Provider detection, configuration, and type classification."""
from __future__ import annotations

from quodeq.analysis._provider_cache import get_provider_configs as _get_cached_configs


def get_provider_configs() -> dict[str, dict]:
    """Return all provider configurations from ai_providers.json."""
    return _get_cached_configs()


def get_provider_type(provider_id: str) -> str:
    """Return 'cli' or 'api' for a provider ID."""
    configs = get_provider_configs()
    return configs.get(provider_id, {}).get("type", "cli")


_LOCAL_API_MARKERS = {"11434", "localhost", "127.0.0.1", "ollama"}


def _is_local_api(provider_id: str) -> bool:
    """Check if an API provider is local (e.g. Ollama)."""
    configs = get_provider_configs()
    cfg = configs.get(provider_id, {})
    api_base = cfg.get("api_base", "")
    return any(marker in api_base.lower() for marker in _LOCAL_API_MARKERS)


def classify_provider(provider_id: str) -> str:
    """Classify a provider as 'cli', 'local-api', or 'cloud-api'."""
    ptype = get_provider_type(provider_id)
    if ptype == "cli":
        return "cli"
    if _is_local_api(provider_id):
        return "local-api"
    return "cloud-api"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm_bridge/test_providers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/llm_bridge/__init__.py src/quodeq/llm_bridge/_providers.py tests/llm_bridge/__init__.py tests/llm_bridge/test_providers.py
git commit -m "feat(llm_bridge): provider detection and classification"
```

---

### Task 2: llm_bridge — Ollama Status & Models

**Files:**
- Create: `src/quodeq/llm_bridge/_ollama.py`
- Test: `tests/llm_bridge/test_ollama.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm_bridge/test_ollama.py
"""Tests for Ollama integration in llm_bridge."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from quodeq.llm_bridge._ollama import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
)


class TestGetOllamaStatus:
    def test_running(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"version":"0.20.2"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", return_value=mock_resp):
            result = get_ollama_status()

        assert result["running"] is True
        assert result["version"] == "0.20.2"

    def test_not_running(self):
        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = get_ollama_status()

        assert result["running"] is False
        assert "error" in result


class TestListOllamaModels:
    def test_returns_models(self):
        mock_data = {
            "models": [
                {
                    "name": "gemma4:26b",
                    "size": 34088653984,
                    "details": {"quantization_level": "Q4_K_M", "family": "gemma4"},
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", return_value=mock_resp):
            models = list_ollama_models()

        assert len(models) == 1
        assert models[0]["name"] == "gemma4:26b"
        assert models[0]["size"] == 34088653984

    def test_server_offline(self):
        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            models = list_ollama_models()

        assert models == []


class TestEstimateMaxAgents:
    def test_small_model_high_memory(self):
        result = estimate_max_agents(model_size=14e9, gpu_memory=48e9)
        assert result["estimate"] >= 2

    def test_large_model_limited_memory(self):
        result = estimate_max_agents(model_size=34e9, gpu_memory=48e9)
        assert result["estimate"] >= 1

    def test_model_exceeds_memory(self):
        result = estimate_max_agents(model_size=80e9, gpu_memory=48e9)
        assert result["estimate"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm_bridge/test_ollama.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/quodeq/llm_bridge/_ollama.py
"""Ollama-specific integration: server status, model list, VRAM estimation."""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error

_log = logging.getLogger(__name__)

_OLLAMA_BASE = "http://localhost:11434"
_TIMEOUT_S = 3


def get_ollama_status(base_url: str = _OLLAMA_BASE) -> dict:
    """Check if the Ollama server is running."""
    try:
        req = urllib.request.Request(f"{base_url}/api/version")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return {
                "running": True,
                "version": data.get("version", "unknown"),
                "address": base_url.replace("http://", ""),
            }
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        return {"running": False, "error": str(exc)}


def list_ollama_models(base_url: str = _OLLAMA_BASE) -> list[dict]:
    """List installed Ollama models."""
    try:
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            return [
                {
                    "name": m["name"],
                    "size": m.get("size", 0),
                    "quantization": m.get("details", {}).get("quantization_level", ""),
                    "family": m.get("details", {}).get("family", ""),
                }
                for m in models
            ]
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        _log.warning("Could not list Ollama models: %s", exc)
        return []


def get_running_model_info(base_url: str = _OLLAMA_BASE) -> dict | None:
    """Get info about the currently loaded model (from /api/ps)."""
    try:
        req = urllib.request.Request(f"{base_url}/api/ps")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            if models:
                m = models[0]
                return {
                    "name": m["name"],
                    "size": m.get("size", 0),
                    "size_vram": m.get("size_vram", 0),
                }
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        pass
    return None


def estimate_max_agents(
    model_size: float,
    gpu_memory: float,
    overhead_factor: float = 1.3,
) -> dict:
    """Estimate max parallel agents from model size and GPU memory.

    Each parallel context needs roughly the model size in memory.
    The overhead_factor accounts for KV cache and runtime overhead.
    """
    if model_size <= 0 or gpu_memory <= 0:
        return {"estimate": 1, "model_size": model_size, "gpu_memory": gpu_memory}

    effective_size = model_size * overhead_factor
    max_contexts = int(gpu_memory / effective_size)
    estimate = max(1, min(max_contexts, 5))

    return {
        "estimate": estimate,
        "model_size": model_size,
        "gpu_memory": gpu_memory,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm_bridge/test_ollama.py -v`
Expected: PASS

- [ ] **Step 5: Update llm_bridge __init__.py**

```python
# Add to src/quodeq/llm_bridge/__init__.py
from quodeq.llm_bridge._ollama import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
)

# Add to __all__:
# "get_ollama_status",
# "list_ollama_models",
# "estimate_max_agents",
```

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/llm_bridge/_ollama.py src/quodeq/llm_bridge/__init__.py tests/llm_bridge/test_ollama.py
git commit -m "feat(llm_bridge): Ollama status, model list, and VRAM estimation"
```

---

### Task 3: llm_bridge — Cloud API Testing

**Files:**
- Create: `src/quodeq/llm_bridge/_cloud.py`
- Test: `tests/llm_bridge/test_cloud.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm_bridge/test_cloud.py
"""Tests for cloud API provider testing."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from quodeq.llm_bridge._cloud import test_cloud_connection


class TestCloudConnection:
    def test_successful_connection(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "hi"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("quodeq.llm_bridge._cloud.openai") as mock_openai:
            mock_openai.OpenAI.return_value = mock_client
            result = test_cloud_connection(
                api_base="https://openrouter.ai/api/v1",
                model="test-model",
                api_key="sk-test",
            )

        assert result["success"] is True
        assert "latency_ms" in result

    def test_auth_failure(self):
        with patch("quodeq.llm_bridge._cloud.openai") as mock_openai:
            mock_openai.OpenAI.return_value.chat.completions.create.side_effect = Exception("401 Unauthorized")
            result = test_cloud_connection(
                api_base="https://openrouter.ai/api/v1",
                model="test-model",
                api_key="bad-key",
            )

        assert result["success"] is False
        assert "401" in result["error"]

    def test_missing_openai_package(self):
        with patch("quodeq.llm_bridge._cloud.openai", None):
            result = test_cloud_connection(
                api_base="https://example.com/v1",
                model="test",
                api_key="test",
            )

        assert result["success"] is False
        assert "openai" in result["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm_bridge/test_cloud.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/quodeq/llm_bridge/_cloud.py
"""Cloud API provider testing — connection verification."""
from __future__ import annotations

import logging
import time

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)


def test_cloud_connection(
    *,
    api_base: str,
    model: str,
    api_key: str,
) -> dict:
    """Test a cloud API provider connection with a minimal request."""
    if openai is None:
        return {"success": False, "error": "openai package not installed. Install with: pip install 'quodeq[api]'"}

    try:
        client = openai.OpenAI(base_url=api_base, api_key=api_key)
        start = time.monotonic()
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        latency = int((time.monotonic() - start) * 1000)
        return {"success": True, "model": model, "latency_ms": latency}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm_bridge/test_cloud.py -v`
Expected: PASS

- [ ] **Step 5: Update llm_bridge __init__.py**

Add `test_cloud_connection` to imports and `__all__`.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/llm_bridge/_cloud.py src/quodeq/llm_bridge/__init__.py tests/llm_bridge/test_cloud.py
git commit -m "feat(llm_bridge): cloud API connection testing"
```

---

### Task 4: llm_bridge — Known Models

**Files:**
- Create: `src/quodeq/llm_bridge/_models.py`
- Create: `src/quodeq/data/config/known_models.json`
- Test: `tests/llm_bridge/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm_bridge/test_models.py
"""Tests for known model suggestions."""
from __future__ import annotations

import pytest

from quodeq.llm_bridge._models import get_known_models


class TestGetKnownModels:
    def test_returns_dict(self):
        models = get_known_models()
        assert isinstance(models, dict)

    def test_claude_has_models(self):
        models = get_known_models()
        assert "claude" in models
        assert len(models["claude"]) > 0

    def test_model_has_required_fields(self):
        models = get_known_models()
        for provider, model_list in models.items():
            for m in model_list:
                assert "id" in m, f"Missing 'id' in {provider} model"
                assert "label" in m, f"Missing 'label' in {provider} model"
                assert "tier" in m, f"Missing 'tier' in {provider} model"

    def test_tiers_are_valid(self):
        valid_tiers = {"fast", "balanced", "thorough"}
        models = get_known_models()
        for provider, model_list in models.items():
            for m in model_list:
                assert m["tier"] in valid_tiers, f"Invalid tier '{m['tier']}' in {provider}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm_bridge/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create known_models.json**

```json
{
  "claude": [
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "tier": "fast"},
    {"id": "claude-sonnet-4-6-20260407", "label": "Sonnet 4.6", "tier": "balanced"},
    {"id": "claude-opus-4-6-20260407", "label": "Opus 4.6", "tier": "thorough"}
  ],
  "codex": [
    {"id": "gpt-4o-mini", "label": "GPT-4o Mini", "tier": "fast"},
    {"id": "gpt-4o", "label": "GPT-4o", "tier": "balanced"},
    {"id": "o3", "label": "o3", "tier": "thorough"}
  ],
  "gemini-cli": [
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "fast"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "tier": "thorough"}
  ]
}
```

Save to: `src/quodeq/data/config/known_models.json`

- [ ] **Step 4: Write implementation**

```python
# src/quodeq/llm_bridge/_models.py
"""Known model suggestions for CLI providers."""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_KNOWN_MODELS: dict | None = None


def _models_path() -> Path:
    """Path to known_models.json."""
    return Path(__file__).resolve().parent.parent / "data" / "config" / "known_models.json"


def get_known_models() -> dict[str, list[dict]]:
    """Load known model suggestions per CLI provider."""
    global _KNOWN_MODELS
    if _KNOWN_MODELS is not None:
        return _KNOWN_MODELS
    try:
        _KNOWN_MODELS = json.loads(_models_path().read_text())
        return _KNOWN_MODELS
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("Could not load known_models.json: %s", exc)
        return {}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/llm_bridge/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Update llm_bridge __init__.py**

Add `get_known_models` to imports and `__all__`.

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/llm_bridge/_models.py src/quodeq/data/config/known_models.json src/quodeq/llm_bridge/__init__.py tests/llm_bridge/test_models.py
git commit -m "feat(llm_bridge): known model suggestions for CLI providers"
```

---

### Task 5: llm_bridge — Concurrency Test

**Files:**
- Modify: `src/quodeq/llm_bridge/_ollama.py`
- Test: `tests/llm_bridge/test_ollama.py` (add tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/llm_bridge/test_ollama.py`:

```python
from quodeq.llm_bridge._ollama import test_concurrency


class TestConcurrency:
    def test_returns_results(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", return_value=mock_resp):
            result = test_concurrency("gemma4:26b", max_agents=3)

        assert "recommended" in result
        assert "results" in result
        assert len(result["results"]) > 0

    def test_server_offline(self):
        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = test_concurrency("gemma4:26b", max_agents=3)

        assert result["recommended"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm_bridge/test_ollama.py::TestConcurrency -v`
Expected: FAIL — `ImportError: cannot import name 'test_concurrency'`

- [ ] **Step 3: Implement test_concurrency**

Add to `src/quodeq/llm_bridge/_ollama.py`:

```python
import concurrent.futures
import time


def _send_small_request(base_url: str, model: str) -> float:
    """Send a minimal completion request, return response time in ms."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
    return (time.monotonic() - start) * 1000


def test_concurrency(
    model: str,
    max_agents: int = 5,
    base_url: str = _OLLAMA_BASE,
) -> dict:
    """Test concurrent inference to find optimal agent count.

    Sends progressively more parallel requests. Stops when latency
    doubles or requests fail.
    """
    results = []
    baseline_ms = None

    for n in range(1, max_agents + 1):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
                futures = [pool.submit(_send_small_request, base_url, model) for _ in range(n)]
                times = [f.result() for f in futures]

            avg_ms = sum(times) / len(times)
            if baseline_ms is None:
                baseline_ms = avg_ms

            if avg_ms > baseline_ms * 2.5:
                results.append({"agents": n, "avg_ms": int(avg_ms), "status": "degraded"})
                break

            results.append({"agents": n, "avg_ms": int(avg_ms), "status": "ok"})
        except Exception:
            results.append({"agents": n, "avg_ms": None, "status": "failed"})
            break

    ok_results = [r for r in results if r["status"] == "ok"]
    recommended = ok_results[-1]["agents"] if ok_results else 1

    return {"recommended": recommended, "results": results}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm_bridge/test_ollama.py -v`
Expected: PASS

- [ ] **Step 5: Update llm_bridge __init__.py**

Add `test_concurrency` to imports and `__all__`.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/llm_bridge/_ollama.py src/quodeq/llm_bridge/__init__.py tests/llm_bridge/test_ollama.py
git commit -m "feat(llm_bridge): concurrent agent testing for Ollama"
```

---

### Task 6: API Routes for llm_bridge

**Files:**
- Create: `src/quodeq/api/llm_bridge_routes.py`
- Modify: `src/quodeq/api/routes_registry.py`
- Test: `tests/api/test_llm_bridge_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_llm_bridge_routes.py
"""Tests for llm_bridge API routes."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def client(tmp_path):
    from quodeq.api.app import create_app
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


class TestOllamaStatus:
    def test_returns_status(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_ollama_status") as mock:
            mock.return_value = {"running": True, "version": "0.20.2", "address": "localhost:11434"}
            resp = client.get("/api/ollama/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["running"] is True


class TestOllamaModels:
    def test_returns_models(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_ollama_models") as mock:
            mock.return_value = [{"name": "gemma4:26b", "size": 34e9, "quantization": "Q4_K_M", "family": "gemma4"}]
            resp = client.get("/api/ollama/models")

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["models"]) == 1


class TestProviderTest:
    def test_success(self, client):
        with patch("quodeq.api.llm_bridge_routes.test_cloud_connection") as mock:
            mock.return_value = {"success": True, "model": "test", "latency_ms": 200}
            resp = client.post("/api/provider/test", json={
                "provider": "openrouter",
                "model": "test",
                "api_base": "https://example.com/v1",
                "api_key": "sk-test",
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestKnownModels:
    def test_returns_models(self, client):
        resp = client.get("/api/known-models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "claude" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_llm_bridge_routes.py -v`
Expected: FAIL — routes not registered

- [ ] **Step 3: Create the routes module**

```python
# src/quodeq/api/llm_bridge_routes.py
"""API routes for LLM bridge — provider status, models, testing."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.llm_bridge import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
    test_concurrency,
    get_known_models,
)
from quodeq.llm_bridge._cloud import test_cloud_connection


def register_llm_bridge_routes(app: Flask) -> None:
    """Register all llm_bridge API routes."""

    @app.get("/api/ollama/status")
    def ollama_status() -> Response:
        return jsonify(get_ollama_status())

    @app.get("/api/ollama/models")
    def ollama_models() -> Response:
        return jsonify({"models": list_ollama_models()})

    @app.post("/api/ollama/test-concurrency")
    def ollama_test_concurrency() -> Response:
        data = request.get_json() or {}
        model = data.get("model", "")
        if not model:
            return jsonify({"error": "model is required"}), 400
        result = test_concurrency(model)
        return jsonify(result)

    @app.post("/api/ollama/estimate-agents")
    def ollama_estimate_agents() -> Response:
        data = request.get_json() or {}
        model_size = data.get("model_size", 0)
        gpu_memory = data.get("gpu_memory", 0)
        return jsonify(estimate_max_agents(model_size=model_size, gpu_memory=gpu_memory))

    @app.post("/api/provider/test")
    def provider_test() -> Response:
        data = request.get_json() or {}
        result = test_cloud_connection(
            api_base=data.get("api_base", ""),
            model=data.get("model", ""),
            api_key=data.get("api_key", ""),
        )
        return jsonify(result)

    @app.get("/api/known-models")
    def known_models() -> Response:
        return jsonify(get_known_models())
```

- [ ] **Step 4: Register routes in routes_registry.py**

Find the `register_all_routes` function in `src/quodeq/api/routes_registry.py` and add:

```python
from quodeq.api.llm_bridge_routes import register_llm_bridge_routes

# Inside register_all_routes():
register_llm_bridge_routes(app)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/api/test_llm_bridge_routes.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/api/llm_bridge_routes.py src/quodeq/api/routes_registry.py tests/api/test_llm_bridge_routes.py
git commit -m "feat(api): llm_bridge routes — ollama status, models, testing"
```

---

### Task 7: Frontend API Layer

**Files:**
- Modify: `src/quodeq/ui/src/api/index.js`

- [ ] **Step 1: Add API functions for llm_bridge endpoints**

Add to `src/quodeq/ui/src/api/index.js`:

```javascript
export async function getOllamaStatus() {
  return request('/ollama/status');
}

export async function getOllamaModels() {
  const data = await request('/ollama/models');
  return data?.models ?? [];
}

export async function testOllamaConcurrency(model) {
  return request('/ollama/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
}

export async function testProviderConnection({ apiBase, model, apiKey }) {
  return request('/provider/test', {
    method: 'POST',
    body: JSON.stringify({ api_base: apiBase, model, api_key: apiKey }),
  });
}

export async function getKnownModels() {
  return request('/known-models');
}
```

- [ ] **Step 2: Commit**

```bash
git add src/quodeq/ui/src/api/index.js
git commit -m "feat(ui): API functions for llm_bridge endpoints"
```

---

### Task 8: Provider Tabs — State Hook

**Files:**
- Create: `src/quodeq/ui/src/features/settings/hooks/useProviderSettings.js`
- Modify: `src/quodeq/ui/src/constants.js`

- [ ] **Step 1: Add new constants**

Add to `src/quodeq/ui/src/constants.js`:

```javascript
export const ACTIVE_PROVIDER_KEY = 'cc-active-provider';

export function providerKey(providerId, setting) {
  return `cc-${providerId}-${setting}`;
}
```

- [ ] **Step 2: Create the provider settings hook**

```javascript
// src/quodeq/ui/src/features/settings/hooks/useProviderSettings.js
import { useState, useCallback } from 'react';
import { providerKey } from '../../../constants.js';

const SETTINGS = ['model', 'model-fast', 'model-balanced', 'model-thorough', 'subagents', 'pool-budget', 'per-dimension', 'verify'];
const DEFAULTS = {
  'model': '',
  'model-fast': '',
  'model-balanced': '',
  'model-thorough': '',
  'subagents': '1',
  'pool-budget': '0',
  'per-dimension': 'true',
  'verify': 'true',
};

function loadProviderState(providerId) {
  const state = {};
  for (const key of SETTINGS) {
    state[key] = localStorage.getItem(providerKey(providerId, key)) ?? DEFAULTS[key];
  }
  return state;
}

function saveProviderSetting(providerId, key, value) {
  localStorage.setItem(providerKey(providerId, key), String(value));
}

export default function useProviderSettings(providerId) {
  const [state, setState] = useState(() => loadProviderState(providerId));

  const update = useCallback((key, value) => {
    setState(prev => ({ ...prev, [key]: String(value) }));
    saveProviderSetting(providerId, key, value);
  }, [providerId]);

  return { state, update };
}
```

- [ ] **Step 3: Commit**

```bash
git add src/quodeq/ui/src/features/settings/hooks/useProviderSettings.js src/quodeq/ui/src/constants.js
git commit -m "feat(ui): per-provider settings state hook with localStorage"
```

---

### Task 9: Provider Tabs — UI Components

**Files:**
- Create: `src/quodeq/ui/src/features/settings/components/ProviderTabs.jsx`
- Create: `src/quodeq/ui/src/features/settings/components/OllamaTab.jsx`
- Create: `src/quodeq/ui/src/features/settings/components/CliProviderTab.jsx`
- Create: `src/quodeq/ui/src/features/settings/components/CloudProviderTab.jsx`
- Create: `src/quodeq/ui/src/features/settings/components/ProviderSettings.jsx`
- Create: `src/quodeq/ui/src/features/settings/components/ServerStatus.jsx`

This is the largest task. Each component is focused:

- [ ] **Step 1: Create ServerStatus component**

```jsx
// src/quodeq/ui/src/features/settings/components/ServerStatus.jsx
import { useState, useEffect } from 'react';
import { getOllamaStatus } from '../../../api/index.js';

export default function ServerStatus() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    getOllamaStatus().then(setStatus).catch(() => setStatus({ running: false, error: 'Could not reach server' }));
    const interval = setInterval(() => {
      getOllamaStatus().then(setStatus).catch(() => setStatus({ running: false, error: 'Connection lost' }));
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  if (!status) return null;

  if (status.running) {
    return (
      <div className="server-status server-status--online">
        <span className="server-dot server-dot--online" />
        <span>Server running</span>
        <span className="server-address">{status.address}</span>
      </div>
    );
  }

  return (
    <div className="server-status server-status--offline">
      <span className="server-dot server-dot--offline" />
      <span>Server offline — Run <code>ollama serve</code> or open the Ollama app</span>
    </div>
  );
}
```

- [ ] **Step 2: Create ProviderSettings component (shared settings form)**

```jsx
// src/quodeq/ui/src/features/settings/components/ProviderSettings.jsx

export default function ProviderSettings({ state, update, providerType }) {
  const subagents = parseInt(state['subagents'] || '1', 10);
  const poolBudget = parseInt(state['pool-budget'] || '0', 10);
  const perDimension = state['per-dimension'] !== 'false';
  const verify = state['verify'] !== 'false';
  const unlimited = poolBudget === 0;

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Max parallel agents</span>
          <span className="settings-description">Number of subagents to run in parallel</span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={1}
          max={10}
          value={subagents}
          onBlur={(e) => update('subagents', Math.max(1, Math.min(10, parseInt(e.target.value, 10) || 1)))}
          onChange={(e) => update('subagents', e.target.value)}
        />
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis time limit</span>
          <span className="settings-description">Max time per dimension. Unlimited runs until all files processed.</span>
        </div>
        <div className="settings-budget-control">
          <div className="theme-toggle">
            <button type="button" className={`theme-toggle-btn${unlimited ? ' active' : ''}`} onClick={() => update('pool-budget', '0')}>Unlimited</button>
            <button type="button" className={`theme-toggle-btn${!unlimited ? ' active' : ''}`} onClick={() => update('pool-budget', '600')}>Limited</button>
          </div>
          <input
            type="number"
            className="settings-model-input"
            min={1}
            max={60}
            value={unlimited ? '' : Math.round(poolBudget / 60)}
            placeholder={unlimited ? '∞' : 'min'}
            disabled={unlimited}
            onChange={(e) => update('pool-budget', String(parseInt(e.target.value || '10', 10) * 60))}
          />
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis mode</span>
          <span className="settings-description">Per-dimension gives deeper coverage per quality area</span>
        </div>
        <div className="theme-toggle">
          <button type="button" className={`theme-toggle-btn${perDimension ? ' active' : ''}`} onClick={() => update('per-dimension', 'true')}>Per-dimension</button>
          <button type="button" className={`theme-toggle-btn${!perDimension ? ' active' : ''}`} onClick={() => update('per-dimension', 'false')}>Grouped</button>
        </div>
      </div>

      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">Verify findings</span>
          <span className="settings-description">Re-check findings from previous runs against current code</span>
        </div>
        <div className="theme-toggle">
          <button type="button" className={`theme-toggle-btn${verify ? ' active' : ''}`} onClick={() => update('verify', 'true')}>On</button>
          <button type="button" className={`theme-toggle-btn${!verify ? ' active' : ''}`} onClick={() => update('verify', 'false')}>Off</button>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 3: Create OllamaTab**

```jsx
// src/quodeq/ui/src/features/settings/components/OllamaTab.jsx
import { useState, useEffect } from 'react';
import { getOllamaModels, testOllamaConcurrency } from '../../../api/index.js';
import ServerStatus from './ServerStatus.jsx';
import ProviderSettings from './ProviderSettings.jsx';

function ModelSelector({ label, value, models, onChange }) {
  return (
    <div className="settings-model-field">
      {label && <label className="settings-model-label">{label}</label>}
      <select className="settings-model-input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Click to select</option>
        {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
      </select>
    </div>
  );
}

export default function OllamaTab({ state, update }) {
  const [models, setModels] = useState([]);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    getOllamaModels().then(setModels).catch(() => setModels([]));
  }, []);

  const runTest = async () => {
    if (!state.model) return;
    setTesting(true);
    try {
      const result = await testOllamaConcurrency(state.model);
      setTestResult(result);
      if (result.recommended) update('subagents', String(result.recommended));
    } catch { setTestResult(null); }
    setTesting(false);
  };

  return (
    <>
      <ServerStatus />
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model</span>
          <span className="settings-description">Select from installed Ollama models</span>
        </div>
        <ModelSelector value={state.model} models={models} onChange={(v) => update('model', v)} />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis models</span>
          <span className="settings-description">Select models for each analysis power level</span>
        </div>
        <div className="settings-model-overrides">
          <ModelSelector label="Fast" value={state['model-fast']} models={models} onChange={(v) => update('model-fast', v)} />
          <ModelSelector label="Balanced" value={state['model-balanced']} models={models} onChange={(v) => update('model-balanced', v)} />
          <ModelSelector label="Thorough" value={state['model-thorough']} models={models} onChange={(v) => update('model-thorough', v)} />
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Max parallel agents</span>
          <span className="settings-description">Auto-detected from VRAM. Test for accuracy.</span>
        </div>
        <div className="settings-budget-control">
          <input type="number" className="settings-model-input" min={1} max={10} value={state.subagents} onChange={(e) => update('subagents', e.target.value)} />
          <button type="button" className="evaluate-submit-btn" onClick={runTest} disabled={testing || !state.model}>
            {testing ? 'Testing...' : 'Auto-detect'}
          </button>
        </div>
        {testResult && <span className="settings-description">Recommended: {testResult.recommended} agents</span>}
      </div>
      <ProviderSettings state={state} update={update} providerType="local-api" />
    </>
  );
}
```

- [ ] **Step 4: Create CliProviderTab**

```jsx
// src/quodeq/ui/src/features/settings/components/CliProviderTab.jsx
import { useState, useEffect } from 'react';
import { getKnownModels } from '../../../api/index.js';
import ProviderSettings from './ProviderSettings.jsx';

function ModelSuggestInput({ label, value, suggestions, onChange }) {
  return (
    <div className="settings-model-field">
      {label && <label className="settings-model-label">{label}</label>}
      <input
        type="text"
        className="settings-model-input"
        list={`models-${label}`}
        value={value}
        placeholder="Select or type model"
        onChange={(e) => onChange(e.target.value)}
      />
      <datalist id={`models-${label}`}>
        {suggestions.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
      </datalist>
    </div>
  );
}

export default function CliProviderTab({ providerId, state, update }) {
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    getKnownModels()
      .then((data) => setSuggestions(data[providerId] || []))
      .catch(() => setSuggestions([]));
  }, [providerId]);

  const fast = suggestions.filter((m) => m.tier === 'fast');
  const balanced = suggestions.filter((m) => m.tier === 'balanced');
  const thorough = suggestions.filter((m) => m.tier === 'thorough');

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model</span>
          <span className="settings-description">Override the default model. Leave blank to use client default.</span>
        </div>
        <ModelSuggestInput value={state.model} suggestions={suggestions} onChange={(v) => update('model', v)} />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis models</span>
          <span className="settings-description">Override models per power level</span>
        </div>
        <div className="settings-model-overrides">
          <ModelSuggestInput label="Fast" value={state['model-fast']} suggestions={fast.length ? fast : suggestions} onChange={(v) => update('model-fast', v)} />
          <ModelSuggestInput label="Balanced" value={state['model-balanced']} suggestions={balanced.length ? balanced : suggestions} onChange={(v) => update('model-balanced', v)} />
          <ModelSuggestInput label="Thorough" value={state['model-thorough']} suggestions={thorough.length ? thorough : suggestions} onChange={(v) => update('model-thorough', v)} />
        </div>
      </div>
      <ProviderSettings state={state} update={update} providerType="cli" />
    </>
  );
}
```

- [ ] **Step 5: Create CloudProviderTab**

```jsx
// src/quodeq/ui/src/features/settings/components/CloudProviderTab.jsx
import { useState } from 'react';
import { testProviderConnection } from '../../../api/index.js';
import ProviderSettings from './ProviderSettings.jsx';

export default function CloudProviderTab({ providerId, providerConfig, state, update }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const browseUrl = providerConfig?.browse_url || '';

  const runTest = async () => {
    setTesting(true);
    try {
      const result = await testProviderConnection({
        apiBase: providerConfig?.api_base || '',
        model: state.model,
        apiKey: '', // read from env on backend
      });
      setTestResult(result);
    } catch { setTestResult({ success: false, error: 'Connection failed' }); }
    setTesting(false);
  };

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model</span>
          <span className="settings-description">
            Enter the model identifier.
            {browseUrl && <> <a href={browseUrl} target="_blank" rel="noopener noreferrer">Browse models</a></>}
          </span>
        </div>
        <div className="settings-budget-control">
          <input
            type="text"
            className="settings-model-input"
            value={state.model}
            placeholder="e.g. qwen/qwen3.6-plus-preview:free"
            onChange={(e) => update('model', e.target.value)}
          />
          <button type="button" className="evaluate-submit-btn" onClick={runTest} disabled={testing || !state.model}>
            {testing ? 'Testing...' : 'Test'}
          </button>
        </div>
        {testResult && (
          <span className={`settings-description ${testResult.success ? '' : 'settings-error'}`}>
            {testResult.success ? `Connected (${testResult.latency_ms}ms)` : testResult.error}
          </span>
        )}
      </div>
      <ProviderSettings state={state} update={update} providerType="cloud-api" />
    </>
  );
}
```

- [ ] **Step 6: Create ProviderTabs (container)**

```jsx
// src/quodeq/ui/src/features/settings/components/ProviderTabs.jsx
import { useState, useEffect } from 'react';
import { getAiClients, getOllamaStatus } from '../../../api/index.js';
import { ACTIVE_PROVIDER_KEY } from '../../../constants.js';
import useProviderSettings from '../hooks/useProviderSettings.js';
import { classify_provider } from './providerUtils.js';
import OllamaTab from './OllamaTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';

function TabContent({ provider, providerConfig }) {
  const classification = classify_provider(provider.id, provider.type, providerConfig);
  const { state, update } = useProviderSettings(provider.id);

  if (classification === 'local-api') {
    return <OllamaTab state={state} update={update} />;
  }
  if (classification === 'cli') {
    return <CliProviderTab providerId={provider.id} state={state} update={update} />;
  }
  return <CloudProviderTab providerId={provider.id} providerConfig={providerConfig} state={state} update={update} />;
}

export default function ProviderTabs({ providerConfigs }) {
  const [clients, setClients] = useState([]);
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem(ACTIVE_PROVIDER_KEY) || '');
  const [statuses, setStatuses] = useState({});

  useEffect(() => {
    getAiClients().then((data) => {
      const list = data.clients || [];
      setClients(list);
      if (!activeTab && list.length > 0) {
        setActiveTab(list[0].id);
        localStorage.setItem(ACTIVE_PROVIDER_KEY, list[0].id);
      }
    }).catch(() => setClients([]));
  }, []);

  useEffect(() => {
    // Check Ollama status for the dot indicator
    const ollama = clients.find((c) => c.id === 'ollama');
    if (ollama) {
      getOllamaStatus()
        .then((s) => setStatuses((prev) => ({ ...prev, ollama: s.running })))
        .catch(() => setStatuses((prev) => ({ ...prev, ollama: false })));
    }
  }, [clients]);

  const selectTab = (id) => {
    setActiveTab(id);
    localStorage.setItem(ACTIVE_PROVIDER_KEY, id);
  };

  const active = clients.find((c) => c.id === activeTab);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <h2 className="settings-section-title">Analysis</h2>
      </div>
      <div className="provider-tab-bar">
        {clients.map((c) => {
          const isActive = c.id === activeTab;
          const status = statuses[c.id];
          const dotClass = status === true ? 'server-dot--online' : status === false ? 'server-dot--offline' : 'server-dot--unknown';
          return (
            <button
              key={c.id}
              type="button"
              className={`provider-tab${isActive ? ' provider-tab--active' : ''}`}
              onClick={() => selectTab(c.id)}
            >
              <span className={`server-dot ${dotClass}`} />
              {c.label}
            </button>
          );
        })}
      </div>
      {active && (
        <div className="provider-tab-content">
          <TabContent provider={active} providerConfig={providerConfigs?.[active.id] || {}} />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 7: Create providerUtils.js helper**

```javascript
// src/quodeq/ui/src/features/settings/components/providerUtils.js
const LOCAL_MARKERS = ['11434', 'localhost', '127.0.0.1', 'ollama'];

export function classify_provider(id, type, config) {
  if (type === 'cli' || !type) return 'cli';
  const apiBase = (config?.api_base || '').toLowerCase();
  if (LOCAL_MARKERS.some((m) => apiBase.includes(m))) return 'local-api';
  return 'cloud-api';
}
```

- [ ] **Step 8: Commit**

```bash
git add src/quodeq/ui/src/features/settings/components/ProviderTabs.jsx \
  src/quodeq/ui/src/features/settings/components/OllamaTab.jsx \
  src/quodeq/ui/src/features/settings/components/CliProviderTab.jsx \
  src/quodeq/ui/src/features/settings/components/CloudProviderTab.jsx \
  src/quodeq/ui/src/features/settings/components/ProviderSettings.jsx \
  src/quodeq/ui/src/features/settings/components/ServerStatus.jsx \
  src/quodeq/ui/src/features/settings/components/providerUtils.js
git commit -m "feat(ui): provider tab components — Ollama, CLI, Cloud"
```

---

### Task 10: Wire ProviderTabs into SettingsPage

**Files:**
- Modify: `src/quodeq/ui/src/features/settings/components/SettingsPage.jsx`
- Modify: `src/quodeq/ui/src/styles/base.css`

- [ ] **Step 1: Replace ModelSection + AnalysisSection with ProviderTabs**

In `SettingsPage.jsx`, replace the Analysis section contents (ModelSection, AnalysisSection, VerificationSection) with:

```jsx
import ProviderTabs from './ProviderTabs.jsx';

// Inside the settings-grid, replace the Analysis section panel with:
<ProviderTabs providerConfigs={providerConfigs} />
```

Remove the now-unused state: `maxSubagents`, `poolBudgetMinutes`, `perDimension`, `availableClients` from `useSettingsState`. Remove `ModelSection`, `AnalysisSection`, `VerificationSection`, `PoolBudgetRow`, `SubagentsRow`, `PerDimensionRow` components.

The `providerConfigs` can be loaded from the existing `get_provider_configs` endpoint or passed from the AI clients response.

- [ ] **Step 2: Add CSS for provider tabs**

Add to `src/quodeq/ui/src/styles/base.css`:

```css
.provider-tab-bar {
  display: flex;
  border-bottom: 2px solid var(--color-border);
  padding: 0 var(--space-4);
  gap: 0;
}

.provider-tab {
  padding: var(--space-3) var(--space-5);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--color-text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.provider-tab--active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
}

.provider-tab:hover:not(.provider-tab--active) {
  color: var(--color-text);
}

.provider-tab-content {
  padding: 0;
}

.server-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.server-dot--online { background: #4ade80; }
.server-dot--offline { background: #f87171; }
.server-dot--unknown { background: var(--color-text-muted); }

.server-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  margin: var(--space-4) var(--space-4) 0;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.server-status--online {
  background: color-mix(in srgb, #4ade80 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, #4ade80 30%, var(--color-border));
  color: #4ade80;
}

.server-status--offline {
  background: color-mix(in srgb, #f87171 10%, var(--color-surface));
  border: 1px solid color-mix(in srgb, #f87171 30%, var(--color-border));
  color: #f87171;
}

.server-address {
  margin-left: auto;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.settings-error {
  color: #f87171;
}
```

- [ ] **Step 3: Build UI**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/features/settings/components/SettingsPage.jsx \
  src/quodeq/ui/src/styles/base.css \
  src/quodeq/static/
git commit -m "feat(ui): wire ProviderTabs into SettingsPage, add tab CSS"
```

---

### Task 11: Wire Provider Settings into Evaluation

**Files:**
- Modify: `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js`
- Modify: `src/quodeq/ui/src/hooks/useEvaluationLifecycle.js`

- [ ] **Step 1: Update preparePayload to read from active provider**

In `useEvaluation.js`, replace the current `preparePayload` function:

```javascript
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

function preparePayload(payload, storage = localStorage) {
  const activeProvider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!activeProvider) return;

  const get = (key) => storage.getItem(providerKey(activeProvider, key));

  payload.aiCmd = activeProvider;
  const model = get('model');
  if (model) payload.aiModel = model;

  const subagents = parseInt(get('subagents') || '1', 10);
  if (subagents !== 1) payload.maxSubagents = subagents;

  const poolBudget = parseInt(get('pool-budget') || '600', 10);
  if (poolBudget !== 600) payload.poolBudget = poolBudget;

  if (get('per-dimension') === 'true') payload.perDimension = true;
  if (get('verify') === 'false') payload.verifyFindings = false;
}
```

- [ ] **Step 2: Update useEvaluationLifecycle to read model tiers from provider**

In `useEvaluationLifecycle.js`, update the evaluation start to read tier models from the active provider:

```javascript
import { ACTIVE_PROVIDER_KEY, providerKey } from '../constants.js';

// Inside startEvaluation call:
const activeProvider = localStorage.getItem(ACTIVE_PROVIDER_KEY) || '';
const get = (key) => localStorage.getItem(providerKey(activeProvider, key));
const subagentModel = get(`model-${['fast', 'balanced', 'thorough'][analysisPower - 1]}`) || undefined;
startEvaluation({ ...payload, subagentModel });
```

- [ ] **Step 3: Build and test**

Run: `cd src/quodeq/ui && npm run build`
Run: `uv run pytest tests/ -q`
Expected: Both pass

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js \
  src/quodeq/ui/src/hooks/useEvaluationLifecycle.js \
  src/quodeq/static/
git commit -m "feat(ui): evaluation reads settings from active provider tab"
```

---

### Task 12: Migration & Cleanup

**Files:**
- Modify: `src/quodeq/ui/src/features/settings/components/ProviderTabs.jsx`
- Remove: `src/quodeq/ui/src/features/settings/components/ModelSection.jsx` (if not already removed)

- [ ] **Step 1: Add migration logic on first load**

Add to `ProviderTabs.jsx`, inside the `useEffect` that loads clients:

```javascript
// Migrate old global settings to active provider
const MIGRATION_KEY = 'cc-provider-tabs-migrated';
if (!localStorage.getItem(MIGRATION_KEY) && list.length > 0) {
  const targetId = localStorage.getItem('cc-ai-cmd') || list[0].id;
  const migrations = {
    'cc-max-subagents': 'subagents',
    'cc-pool-budget': 'pool-budget',
    'cc-per-dimension': 'per-dimension',
    'cc-ai-model': 'model',
  };
  for (const [oldKey, newSuffix] of Object.entries(migrations)) {
    const oldVal = localStorage.getItem(oldKey);
    if (oldVal !== null) {
      localStorage.setItem(`cc-${targetId}-${newSuffix}`, oldVal);
      localStorage.removeItem(oldKey);
    }
  }
  localStorage.setItem(MIGRATION_KEY, '1');
}
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: All pass

- [ ] **Step 3: Build UI final**

Run: `cd src/quodeq/ui && npm run build`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: localStorage migration from global to per-provider settings"
```

---

### Task 13: Full Integration Test

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 2: Manual smoke test**

1. Start dashboard: `uv run quodeq dashboard --dev`
2. Open Settings — verify tabs appear for detected providers
3. If Ollama is running: verify green dot, model dropdown populates
4. Switch tabs — verify each has independent settings
5. Change settings in Ollama tab, switch to Claude tab — verify Ollama settings preserved
6. Start an evaluation — verify it uses the active tab's settings
7. Restart dashboard — verify settings persist from localStorage

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test adjustments"
```
