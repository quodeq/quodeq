"""Cross-cutting ``shared/`` env seams (the non-config files).

Each seam is checked twice -- with a value injected, and with an injected
``{}`` while the process environment carries a different value, which must
be ignored.

``defaults_path`` and ``configure_stdio_utf8``/``source_user_path`` are the
interesting ones: the first used to be a module constant frozen at import
time, and the last two write back into the mapping instead of the process.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from quodeq.shared import frozen
from quodeq.shared._config import _ConfigHolder, defaults_path
from quodeq.shared._io import configure_stdio_utf8
from quodeq.shared._log_format import _should_use_color
from quodeq.shared.logging import _apply_env_log_level, _logger
from quodeq.shared.provider_env import providers_path


class TestDefaultsPath:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DEFAULTS_PATH", str(tmp_path / "from-process.json"))
        injected = tmp_path / "from-env.json"
        assert defaults_path({"QUODEQ_DEFAULTS_PATH": str(injected)}) == injected

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DEFAULTS_PATH", str(tmp_path / "from-process.json"))
        assert defaults_path({}).name == "defaults.json"

    def test_is_read_at_call_time_not_import_time(self, monkeypatch, tmp_path):
        """The old module constant froze this at first import; it no longer does."""
        target = tmp_path / "late.json"
        monkeypatch.setenv("QUODEQ_DEFAULTS_PATH", str(target))
        assert defaults_path() == target


class TestConfigHolderTakesEnv:
    """The holder resolves its defaults file from the mapping it was given."""

    def _defaults_file(self, tmp_path, value: str):
        path = tmp_path / "custom-defaults.json"
        path.write_text(json.dumps({"marker": value}), encoding="utf-8")
        return path

    def test_loads_from_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DEFAULTS_PATH", str(tmp_path / "from-process.json"))
        injected = self._defaults_file(tmp_path, "from-env")
        holder = _ConfigHolder({"QUODEQ_DEFAULTS_PATH": str(injected)})
        assert holder.get()["marker"] == "from-env"

    def test_caches_the_config_after_the_first_load(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DEFAULTS_PATH", str(tmp_path / "from-process.json"))
        injected = self._defaults_file(tmp_path, "from-env")
        holder = _ConfigHolder({"QUODEQ_DEFAULTS_PATH": str(injected)})
        first = holder.get()
        injected.unlink()  # a second read would raise
        assert holder.get() is first

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DEFAULTS_PATH", str(self._defaults_file(tmp_path, "from-process")))
        assert _ConfigHolder({}).get().get("marker") is None


class TestProvidersPath:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_AI_PROVIDERS_PATH", str(tmp_path / "from-process.json"))
        injected = tmp_path / "from-env.json"
        assert providers_path({"QUODEQ_AI_PROVIDERS_PATH": str(injected)}) == injected

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_AI_PROVIDERS_PATH", str(tmp_path / "from-process.json"))
        assert providers_path({}).name == "ai_providers.json"


class TestShouldUseColor:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert _should_use_color({"NO_COLOR": "1"}) is False

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert _should_use_color({}) is True


class TestApplyEnvLogLevel:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        original = _logger.level
        try:
            _apply_env_log_level(env={"LOG_LEVEL": "DEBUG"})
            assert _logger.level == 10
        finally:
            _logger.setLevel(original)

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        original = _logger.level
        try:
            _apply_env_log_level(env={})
            assert _logger.level == original
        finally:
            _logger.setLevel(original)


class TestConfigureStdioUtf8:
    def test_writes_pythonutf8_into_the_injected_mapping(self, monkeypatch):
        monkeypatch.delenv("PYTHONUTF8", raising=False)
        injected: dict[str, str] = {"VAR": "value"}
        configure_stdio_utf8(injected)
        assert injected["PYTHONUTF8"] == "1"
        assert "PYTHONUTF8" not in os.environ

    def test_empty_injected_mapping_is_not_seeded_from_the_process(self, monkeypatch):
        monkeypatch.setenv("PYTHONUTF8", "0")
        injected: dict[str, str] = {}
        configure_stdio_utf8(injected)
        assert injected == {"PYTHONUTF8": "1"}


@pytest.mark.skipif(sys.platform == "win32", reason="source_user_path is a no-op on Windows")
class TestSourceUserPath:
    def test_reads_shell_from_and_writes_path_into_the_injected_mapping(self, monkeypatch):
        monkeypatch.setattr(frozen, "is_frozen", lambda: True)
        monkeypatch.setenv("SHELL", "/bin/bash")
        seen: dict[str, str] = {}

        class _Result:
            returncode = 0
            stdout = "/injected/bin\n"

        def fake_run(argv, **kwargs):
            seen["shell"] = argv[0]
            return _Result()

        monkeypatch.setattr(frozen.subprocess, "run", fake_run)
        injected: dict[str, str] = {"SHELL": "/bin/zsh", "PATH": "/old"}
        frozen.source_user_path(injected)
        assert seen["shell"] == "/bin/zsh"
        assert injected["PATH"] == "/injected/bin"

    def test_empty_injected_mapping_ignores_the_process_shell(self, monkeypatch):
        monkeypatch.setattr(frozen, "is_frozen", lambda: True)
        monkeypatch.setenv("SHELL", "/bin/bash")
        seen: dict[str, str] = {}

        def fake_run(argv, **kwargs):
            seen["shell"] = argv[0]
            raise OSError("no shell")

        monkeypatch.setattr(frozen.subprocess, "run", fake_run)
        injected: dict[str, str] = {}
        frozen.source_user_path(injected)
        # "" from the empty mapping is not in _ALLOWED_SHELLS -> the default.
        assert seen["shell"] == "/bin/zsh"
        # Fallback branch appends to the injected mapping's PATH, not the process's.
        assert injected["PATH"].startswith(":")
        assert str(Path.home() / ".local" / "bin") in injected["PATH"]
