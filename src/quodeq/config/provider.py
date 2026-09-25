"""Per-provider API-key env vars. The Provider vocabulary lives in core.types.provider.

Re-exported here because llm_bridge, menubar and update may import config but
not core (tools/check_imports.py); every existing importer keeps this path.
"""
from __future__ import annotations

from quodeq.core.types.provider import Provider, ProviderType

__all__ = ["PROVIDERS", "Provider", "ProviderType"]


# Provider -> the env var that carries its API key ("" when it needs none).
PROVIDERS: dict[Provider, str] = {
    Provider.CLAUDE: "ANTHROPIC_API_KEY",
    Provider.CODEX: "CODEX_API_KEY",
    Provider.GEMINI: "GEMINI_API_KEY",
    Provider.COPILOT: "",
    Provider.OLLAMA: "",
    Provider.LLAMACPP: "",
    Provider.OPENROUTER: "OPENROUTER_API_KEY",
    Provider.CUSTOM: "AI_API_KEY",
}
