"""normalize_model_id expands codex's bare version shorthand and nothing else.
shared/ may import only core/, so the codex check reads Provider.CODEX from
core.types.provider now that Provider lives there."""
from __future__ import annotations

from quodeq.core.types.provider import Provider
from quodeq.shared.models import normalize_model_id


def test_codex_shorthand_expands():
    assert normalize_model_id(Provider.CODEX, "5.4") == "gpt-5.4"
    assert normalize_model_id("codex", " 5.3-codex ") == "gpt-5.3-codex"


def test_other_providers_keep_the_model_as_written():
    assert normalize_model_id("omlx", "5.4") == "5.4"
    assert normalize_model_id(Provider.CLAUDE, "5.4") == "5.4"
    assert normalize_model_id("codex", "gpt-5.4") == "gpt-5.4"
