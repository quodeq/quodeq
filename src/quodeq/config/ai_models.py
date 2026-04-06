"""Model tier resolution -- maps tier names to concrete model IDs."""
from __future__ import annotations

import os
from enum import StrEnum


class ModelTier(StrEnum):
    """Analysis model tiers, from lightest to heaviest."""

    ORCHESTRATOR = "orchestrator"
    LIGHT = "light"
    MEDIUM = "medium"
    HIGH = "high"


_TIER_ENV_VARS: dict[ModelTier, str] = {
    ModelTier.ORCHESTRATOR: "QUODEQ_MODEL_ORCHESTRATOR",
    ModelTier.LIGHT: "QUODEQ_MODEL_LIGHT",
    ModelTier.MEDIUM: "QUODEQ_MODEL_MEDIUM",
    ModelTier.HIGH: "QUODEQ_MODEL_HIGH",
}


def get_model_for_tier(
    tier: ModelTier,
    *,
    env: dict[str, str] | None = None,
    provider_default: str | None = None,
) -> str | None:
    """Resolve the model name for a given tier.

    Priority: QUODEQ_MODEL_<TIER> > AI_MODEL > provider_default > None
    """
    environ = env if env is not None else os.environ
    tier_var = _TIER_ENV_VARS[tier]
    tier_value = environ.get(tier_var, "").strip()
    if tier_value:
        return tier_value
    ai_model = environ.get("AI_MODEL", "").strip()
    if ai_model:
        return ai_model
    return provider_default
