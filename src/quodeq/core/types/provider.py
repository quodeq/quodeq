"""AI provider vocabulary: the names only.

Selection and persistence live in ``config/ai_provider.py``; the API-key env
var per provider in ``config/provider.py``. A provider-config id with no
member here (``omlx``, a user-named endpoint) is still a valid provider id:
code that must accept those compares strings, never ``Provider(x)``.
"""
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


class ProviderType(StrEnum):
    """How quodeq talks to a provider: a local CLI subprocess or an HTTP API (provider config "type")."""

    CLI = "cli"
    API = "api"
