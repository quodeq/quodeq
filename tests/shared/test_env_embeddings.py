"""Env accessors for the semantic-precedent embedding configuration."""
from quodeq.shared._env import (
    get_embedding_base_url,
    get_embedding_model,
    get_precedent_similarity_threshold,
    semantic_precedents_enabled,
)


def test_embedding_model_default() -> None:
    assert get_embedding_model(env={}) == "nomic-embed-text"


def test_embedding_model_override() -> None:
    assert get_embedding_model(env={"QUODEQ_EMBEDDING_MODEL": "mxbai-embed-large"}) == "mxbai-embed-large"


def test_base_url_default() -> None:
    assert get_embedding_base_url(env={}) == "http://localhost:11434"


def test_base_url_falls_back_to_ollama_base() -> None:
    assert get_embedding_base_url(env={"OLLAMA_BASE_URL": "http://box:11434"}) == "http://box:11434"


def test_base_url_explicit_override_wins() -> None:
    env = {"OLLAMA_BASE_URL": "http://box:11434", "QUODEQ_EMBEDDING_BASE_URL": "http://other:8080"}
    assert get_embedding_base_url(env=env) == "http://other:8080"


def test_flag_default_off() -> None:
    assert semantic_precedents_enabled(env={}) is False


def test_flag_truthy_values() -> None:
    for raw in ("1", "true", "YES", " on "):
        assert semantic_precedents_enabled(env={"QUODEQ_SEMANTIC_PRECEDENTS": raw}) is True
    assert semantic_precedents_enabled(env={"QUODEQ_SEMANTIC_PRECEDENTS": "0"}) is False


def test_threshold_default() -> None:
    assert get_precedent_similarity_threshold(env={}) == 0.85


def test_threshold_override_and_garbage() -> None:
    assert get_precedent_similarity_threshold(env={"QUODEQ_PRECEDENT_SIMILARITY": "0.9"}) == 0.9
    assert get_precedent_similarity_threshold(env={"QUODEQ_PRECEDENT_SIMILARITY": "nope"}) == 0.85
    assert get_precedent_similarity_threshold(env={"QUODEQ_PRECEDENT_SIMILARITY": "7"}) == 0.85
    # Boundary: 0.0 is excluded by the `0.0 < val` check, not just non-positive garbage.
    assert get_precedent_similarity_threshold(env={"QUODEQ_PRECEDENT_SIMILARITY": "0"}) == 0.85
    assert get_precedent_similarity_threshold(env={"QUODEQ_PRECEDENT_SIMILARITY": "-0.5"}) == 0.85
