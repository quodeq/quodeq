"""Embeddings client: order preservation, seams, availability cache."""
from types import SimpleNamespace

import pytest

from quodeq.llm_bridge._embeddings import (
    BATCH_TIMEOUT,
    QUERY_TIMEOUT,
    _client_kwargs,
    _v1_base,
    embed_texts,
    embedding_model_available,
    reset_embedding_availability_cache,
)


class _FakeClient:
    """Scripted OpenAI-style embeddings client (context-manager protocol)."""

    def __init__(self, vectors_by_index: list[list[float]]) -> None:
        self._vectors = vectors_by_index
        self.requests: list[dict] = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, *, model: str, input: list[str]):  # noqa: A002 - SDK arg name
        self.requests.append({"model": model, "input": input})
        # Return items deliberately out of order to prove sorting by index.
        # Only return embeddings for vectors we have available (allows testing count mismatches).
        data = [
            SimpleNamespace(index=i, embedding=self._vectors[i])
            for i in reversed(range(min(len(input), len(self._vectors))))
        ]
        return SimpleNamespace(data=data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_embedding_availability_cache()
    yield
    reset_embedding_availability_cache()


def test_embed_texts_preserves_order() -> None:
    fake = _FakeClient([[1.0, 0.0], [0.0, 1.0]])
    out = embed_texts(
        ["a", "b"], model="m", base_url="http://x", client_factory=lambda: fake,
    )
    assert out == [[1.0, 0.0], [0.0, 1.0]]
    assert fake.requests == [{"model": "m", "input": ["a", "b"]}]


def test_embed_texts_empty_input_short_circuits() -> None:
    def boom():
        raise AssertionError("factory must not be called for empty input")
    assert embed_texts([], model="m", base_url="http://x", client_factory=boom) == []


def test_embed_texts_count_mismatch_raises() -> None:
    fake = _FakeClient([[1.0]])
    with pytest.raises(RuntimeError, match="mismatch"):
        embed_texts(["a", "b"], model="m", base_url="http://x", client_factory=lambda: fake)


def test_availability_uses_lister_and_caches() -> None:
    calls: list[str] = []

    def lister(base_url: str) -> list[dict]:
        calls.append(base_url)
        return [{"name": "nomic-embed-text:latest"}]

    assert embedding_model_available("nomic-embed-text", "http://localhost:11434", lister=lister)
    assert embedding_model_available("nomic-embed-text", "http://localhost:11434", lister=lister)
    assert calls == ["http://localhost:11434"]  # second call served from cache


def test_availability_missing_model() -> None:
    def lister(base_url: str) -> list[dict]:
        return [{"name": "gemma4:26b"}]

    assert not embedding_model_available("nomic-embed-text", "http://localhost:11434", lister=lister)


def test_availability_permissive_for_non_ollama_base() -> None:
    assert embedding_model_available("anything", "http://lan-box:8080")


def test_timeout_profiles_are_short() -> None:
    assert BATCH_TIMEOUT.read == 60.0
    assert QUERY_TIMEOUT.read == 10.0


def test_v1_base_normalization() -> None:
    assert _v1_base("http://localhost:11434") == "http://localhost:11434/v1"
    assert _v1_base("http://localhost:11434/") == "http://localhost:11434/v1"
    assert _v1_base("http://box:8080/v1") == "http://box:8080/v1"


def test_default_client_kwargs() -> None:
    kwargs = _client_kwargs("http://localhost:11434", None, None)
    assert kwargs == {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "timeout": BATCH_TIMEOUT,
        "max_retries": 0,
    }
    assert _client_kwargs("http://x", "key", None)["api_key"] == "key"
