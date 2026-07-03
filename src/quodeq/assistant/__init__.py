"""Embedded LLM assistant: sessions, tools, provider turn adapters."""
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.llm_bridge import LOCAL_PROVIDERS, get_provider_configs

__all__ = ["AssistantRepository", "LOCAL_PROVIDERS", "get_provider_configs"]
