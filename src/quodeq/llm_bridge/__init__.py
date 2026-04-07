"""LLM Bridge — clean interface to LLM providers.

The analysis layer calls this module instead of talking to
Ollama/OpenRouter/CLI tools directly.
"""
from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
)
from quodeq.llm_bridge._ollama import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
    run_concurrency_test,
)
from quodeq.llm_bridge._cloud import check_cloud_connection
from quodeq.llm_bridge._models import get_known_models

__all__ = [
    "get_provider_configs",
    "get_provider_type",
    "classify_provider",
    "get_ollama_status",
    "list_ollama_models",
    "estimate_max_agents",
    "test_concurrency",
    "check_cloud_connection",
    "get_known_models",
]
