"""Tests for model tier resolution."""
from __future__ import annotations

import pytest

from quodeq.config.ai_models import get_model_for_tier, ModelTier


class TestModelTier:
    """Model tier enum values."""

    def test_tier_values(self):
        assert ModelTier.ORCHESTRATOR == "orchestrator"
        assert ModelTier.LIGHT == "light"
        assert ModelTier.MEDIUM == "medium"
        assert ModelTier.HIGH == "high"


class TestGetModelForTier:
    """get_model_for_tier resolves model name from env vars with fallbacks."""

    def test_ai_model_overrides_all_tiers(self):
        env = {"AI_MODEL": "my-model"}
        assert get_model_for_tier(ModelTier.LIGHT, env=env) == "my-model"
        assert get_model_for_tier(ModelTier.HIGH, env=env) == "my-model"

    def test_tier_specific_env_var(self):
        env = {"QUODEQ_MODEL_MEDIUM": "sonnet", "AI_MODEL": "fallback"}
        assert get_model_for_tier(ModelTier.MEDIUM, env=env) == "sonnet"

    def test_tier_env_takes_precedence_over_ai_model(self):
        env = {"QUODEQ_MODEL_HIGH": "opus", "AI_MODEL": "default"}
        assert get_model_for_tier(ModelTier.HIGH, env=env) == "opus"

    def test_falls_back_to_ai_model(self):
        env = {"AI_MODEL": "my-model"}
        assert get_model_for_tier(ModelTier.ORCHESTRATOR, env=env) == "my-model"

    def test_returns_none_when_nothing_set(self):
        assert get_model_for_tier(ModelTier.MEDIUM, env={}) is None

    def test_empty_tier_var_falls_through(self):
        env = {"QUODEQ_MODEL_LIGHT": "", "AI_MODEL": "fallback"}
        assert get_model_for_tier(ModelTier.LIGHT, env=env) == "fallback"

    def test_provider_default_used_as_last_resort(self):
        env = {}
        result = get_model_for_tier(ModelTier.MEDIUM, env=env, provider_default="llama3.1")
        assert result == "llama3.1"

    def test_ai_model_overrides_provider_default(self):
        env = {"AI_MODEL": "custom-model"}
        result = get_model_for_tier(ModelTier.MEDIUM, env=env, provider_default="llama3.1")
        assert result == "custom-model"
