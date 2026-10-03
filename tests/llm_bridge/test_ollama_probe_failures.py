"""Each Ollama probe logs its own warning and returns its own fallback when the server fails."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from quodeq.llm_bridge import get_ollama_status, list_ollama_models, run_concurrency_test

_URLOPEN = "quodeq.llm_bridge._ollama.urllib.request.urlopen"


def _body(raw: bytes) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.mark.parametrize(("probe", "fallback", "message"), [
    (get_ollama_status, {"running": False, "error": "Connection failed"}, "Ollama status check failed: boom"),
    (list_ollama_models, [], "Could not list Ollama models: boom"),
])
def test_a_failed_request_logs_and_falls_back(probe, fallback, message, caplog):
    with caplog.at_level(logging.WARNING), patch(_URLOPEN, side_effect=OSError("boom")):
        assert probe("http://localhost:11434") == fallback
    assert [r.getMessage() for r in caplog.records] == [message]


def test_a_model_entry_without_a_name_is_a_logged_failure(caplog):
    with caplog.at_level(logging.WARNING), patch(_URLOPEN, return_value=_body(b'{"models": [{}]}')):
        assert list_ollama_models("http://localhost:11434") == []
    assert caplog.records[0].getMessage().startswith("Could not list Ollama models: ")


def test_the_running_model_probe_logs_its_own_failure(caplog):
    with caplog.at_level(logging.WARNING), patch(_URLOPEN, side_effect=OSError("boom")), \
            patch("quodeq.llm_bridge._ollama._get_gpu_memory", return_value=8):
        assert run_concurrency_test("m", "http://localhost:11434")["vram_per_context"] == 0
    assert [r.getMessage() for r in caplog.records] == [
        "Could not get running Ollama model info: boom", "Could not list Ollama models: boom",
    ]


def test_no_running_model_falls_back_to_the_listed_size_without_a_warning(caplog):
    bodies = [_body(b'{"models": []}'), _body(b'{"models": [{"name": "m", "size": 7}]}')]
    with caplog.at_level(logging.WARNING), patch(_URLOPEN, side_effect=bodies), \
            patch("quodeq.llm_bridge._ollama._get_gpu_memory", return_value=0):
        assert run_concurrency_test("m", "http://localhost:11434")["vram_per_context"] == 7
    assert caplog.records == []


def test_status_reports_the_address_without_the_scheme():
    with patch(_URLOPEN, return_value=_body(b'{"version": "1.2"}')):
        assert get_ollama_status("http://localhost:11434") == {
            "running": True, "version": "1.2", "address": "localhost:11434",
        }
