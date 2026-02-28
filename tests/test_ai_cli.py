import os

from codecompass.evaluate.lib.ai_cli_provider import get_ai_cmd


def test_get_ai_cmd_defaults_to_claude(monkeypatch):
    monkeypatch.delenv("AI_CMD", raising=False)
    assert get_ai_cmd() == "claude"
