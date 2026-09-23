"""AI provider vocabulary (the names only; selection and persistence live in ai_provider.py)."""
from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    """The AI providers quodeq can drive; the value is the CLI/config name."""

    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    COPILOT = "copilot"
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"


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
