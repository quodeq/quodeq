"""The assistant-only style discriminators (resume_style, session_id_source,
system_prompt_style) agree across their three sides.

_cli_config.py declares them and reads them off the ai_providers.json
"assistant" block; _cli.py and _cli_command.py compare against them to pick
the argv shape for a turn. Nobody may retype the strings: a comparing module
must hold the same object _cli_config does, and every value the packaged
catalog ships must be one of the declared constants -- otherwise a provider
entry silently falls through to the default branch.
"""
from __future__ import annotations

import json

import pytest

from quodeq.assistant.adapters._cli_config import (
    RESUME_STYLE_EXEC, RESUME_STYLE_FLAG_RESUME, RESUME_STYLE_GEMINI,
    SESSION_ID_SOURCE_PARSE_JSONL, SESSION_ID_SOURCE_PREASSIGN,
    SYSTEM_PROMPT_STYLE_ARGV_APPEND, SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX,
)
from quodeq.shared.provider_env import providers_path

_RESUME_STYLES = {RESUME_STYLE_FLAG_RESUME, RESUME_STYLE_EXEC, RESUME_STYLE_GEMINI}
_SESSION_ID_SOURCES = {SESSION_ID_SOURCE_PREASSIGN, SESSION_ID_SOURCE_PARSE_JSONL}
_SYSTEM_PROMPT_STYLES = {SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX, SYSTEM_PROMPT_STYLE_ARGV_APPEND}

# Module that compares a CliChatConfig field against a constant -> the names
# it must share with _cli_config. Keep in step with the comparisons in
# _cli.py and _cli_command.py.
_CONSUMERS = {
    "quodeq.assistant.adapters._cli": ("SYSTEM_PROMPT_STYLE_MESSAGE_PREFIX",),
    "quodeq.assistant.adapters._cli_command": (
        "RESUME_STYLE_GEMINI", "SESSION_ID_SOURCE_PARSE_JSONL", "SYSTEM_PROMPT_STYLE_ARGV_APPEND",
    ),
}


def _catalog():
    return json.loads(providers_path().read_text(encoding="utf-8"))


@pytest.mark.parametrize(("module_name", "names"), sorted(_CONSUMERS.items()))
def test_comparing_modules_use_the_cli_config_constants(module_name, names):
    import importlib

    from quodeq.assistant.adapters import _cli_config

    module = importlib.import_module(module_name)

    for name in names:
        assert getattr(module, name) is getattr(_cli_config, name), f"{module_name}.{name}"


def test_catalog_resume_styles_are_declared_constants():
    for provider_id, cfg in _catalog().items():
        style = cfg.get("assistant", {}).get("resume_style")
        if style is not None:
            assert style in _RESUME_STYLES, f"{provider_id}: unknown resume_style {style!r}"


def test_catalog_session_id_sources_are_declared_constants():
    for provider_id, cfg in _catalog().items():
        source = cfg.get("assistant", {}).get("session_id_source")
        if source is not None:
            assert source in _SESSION_ID_SOURCES, f"{provider_id}: unknown source {source!r}"


def test_catalog_system_prompt_styles_are_declared_constants():
    for provider_id, cfg in _catalog().items():
        style = cfg.get("assistant", {}).get("system_prompt_style")
        if style is not None:
            assert style in _SYSTEM_PROMPT_STYLES, f"{provider_id}: unknown style {style!r}"


def test_the_catalog_actually_exercises_every_declared_style():
    """Guards the three tests above against passing vacuously if the catalog
    ever stops shipping an "assistant" block.
    """
    catalog = _catalog().values()
    seen_resume = {c.get("assistant", {}).get("resume_style") for c in catalog}
    seen_source = {c.get("assistant", {}).get("session_id_source") for c in catalog}
    seen_prompt = {c.get("assistant", {}).get("system_prompt_style") for c in catalog}

    assert _RESUME_STYLES <= seen_resume
    assert _SESSION_ID_SOURCES <= seen_source
    assert _SYSTEM_PROMPT_STYLES <= seen_prompt
