"""LLM Bridge — clean interface to LLM providers.

The analysis layer calls this module instead of talking to
Ollama/OpenRouter/CLI tools directly.
"""
from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
    LOCAL_PROVIDERS,
)
from quodeq.llm_bridge._ollama import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
    run_concurrency_test,
)
from quodeq.llm_bridge._llamacpp import (
    get_llamacpp_status,
    list_llamacpp_models,
    run_concurrency_test as run_llamacpp_concurrency_test,
)
from quodeq.llm_bridge._omlx import (
    get_omlx_status,
    list_omlx_models,
    run_concurrency_test as run_omlx_concurrency_test,
)
from quodeq.llm_bridge._cloud import check_cloud_connection
from quodeq.llm_bridge._embeddings import (
    embed_texts,
    embedding_model_available,
    reset_embedding_availability_cache,
)
from quodeq.llm_bridge._models import get_known_models

__all__ = [
    "get_provider_configs",
    "LOCAL_PROVIDERS",
    "get_provider_type",
    "classify_provider",
    "get_ollama_status",
    "list_ollama_models",
    "estimate_max_agents",
    "run_concurrency_test",
    "get_llamacpp_status",
    "list_llamacpp_models",
    "run_llamacpp_concurrency_test",
    "get_omlx_status",
    "list_omlx_models",
    "run_omlx_concurrency_test",
    "check_cloud_connection",
    "embed_texts",
    "embedding_model_available",
    "reset_embedding_availability_cache",
    "get_known_models",
]
