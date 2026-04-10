"""Tests for known model suggestions."""
from __future__ import annotations

import pytest

from quodeq.llm_bridge._models import get_known_models


class TestGetKnownModels:
    def test_returns_dict(self):
        models = get_known_models()
        assert isinstance(models, dict)

    def test_claude_has_models(self):
        models = get_known_models()
        assert "claude" in models
        assert len(models["claude"]) > 0

    def test_model_has_required_fields(self):
        models = get_known_models()
        for provider, model_list in models.items():
            for m in model_list:
                assert "id" in m, f"Missing 'id' in {provider} model"
                assert "label" in m, f"Missing 'label' in {provider} model"
                assert "tier" in m, f"Missing 'tier' in {provider} model"

    def test_tiers_are_valid(self):
        valid_tiers = {"fast", "balanced", "thorough"}
        models = get_known_models()
        for provider, model_list in models.items():
            for m in model_list:
                assert m["tier"] in valid_tiers, f"Invalid tier '{m['tier']}' in {provider}"
