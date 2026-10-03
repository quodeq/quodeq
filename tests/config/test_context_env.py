"""config.context_env.precedent_settings: one resolver for the semantic tier's env."""
from __future__ import annotations

from quodeq.config.context_env import PrecedentSettings, precedent_settings


def test_defaults_when_unset():
    assert precedent_settings({}) == PrecedentSettings(
        enabled=False, model="nomic-embed-text",
        base_url="http://localhost:11434", similarity_threshold=0.85,
    )


def test_valid_values_are_read():
    settings = precedent_settings({
        "QUODEQ_SEMANTIC_PRECEDENTS": "yes",
        "QUODEQ_EMBEDDING_MODEL": "mxbai",
        "QUODEQ_EMBEDDING_BASE_URL": "http://embed:1",
        "QUODEQ_PRECEDENT_SIMILARITY": "0.9",
    })
    assert settings == PrecedentSettings(
        enabled=True, model="mxbai", base_url="http://embed:1", similarity_threshold=0.9,
    )


def test_base_url_falls_back_to_ollama_base_url():
    assert precedent_settings({"OLLAMA_BASE_URL": "http://ollama:2"}).base_url == "http://ollama:2"


def test_out_of_range_or_invalid_threshold_reads_as_default():
    assert precedent_settings({"QUODEQ_PRECEDENT_SIMILARITY": "1.5"}).similarity_threshold == 0.85
    assert precedent_settings({"QUODEQ_PRECEDENT_SIMILARITY": "high"}).similarity_threshold == 0.85


def test_process_env_fallback_and_injected_env_wins(monkeypatch):
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    monkeypatch.setenv("QUODEQ_PRECEDENT_SIMILARITY", "0.7")
    from_process = precedent_settings()
    assert (from_process.enabled, from_process.similarity_threshold) == (True, 0.7)
    assert precedent_settings({}).enabled is False
