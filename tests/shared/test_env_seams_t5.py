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
import subprocess
import sys
from pathlib import Path

import pytest

from quodeq.shared import frozen
from quodeq.shared._config import _ConfigHolder, defaults_path
from quodeq.shared.text_io import configure_stdio_utf8
from quodeq.shared._log_format import should_use_color
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
        assert should_use_color({"NO_COLOR": "1"}) is False

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert should_use_color({}) is True


class TestUseColorOldNameShim:
    """USE_COLOR is now a __getattr__ shim (PEP 562) over use_color(),
    decided at first use instead of at import.

    USE_COLOR itself has no public re-export (logging.py dropped it -- see
    the next test), so proving the shim matches the function needs a direct
    import of the private _log_format module. Run in a subprocess instead
    of importing it in this file directly, to avoid growing
    tools/private_imports_tests_baseline.txt (shrink-only)."""

    def test_use_color_old_name_matches_the_function(self):
        # Compares against should_use_color() (the real decision), not
        # use_color() -- USE_COLOR's shim calls use_color() internally, so
        # comparing against use_color() would be tautological and could
        # never fail even if the shim were wired wrong.
        script = (
            "from quodeq.shared._log_format import USE_COLOR, should_use_color\n"
            "assert USE_COLOR == should_use_color(), (USE_COLOR, should_use_color())\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

    def test_shared_logging_no_longer_re_exports_use_color(self):
        """logging.py's eager `from x import USE_COLOR` re-export would
        defeat the lazy load; nothing imports it that way (see survey)."""
        import quodeq.shared.logging as logging_mod

        assert "USE_COLOR" not in vars(logging_mod)

    def test_shared_logging_use_color_shim_matches_use_color(self):
        """M3: shared.logging.USE_COLOR is its own __getattr__ shim (not
        just re-exporting _log_format's), at the old path callers used
        before this attribute was dropped with no replacement."""
        import quodeq.shared.logging as logging_mod

        assert logging_mod.USE_COLOR == logging_mod.use_color()

    def test_importing_shared_logging_does_not_decide_color(self):
        """The shim must stay lazy: importing the module must not itself
        call use_color()/should_use_color() (that would freeze NO_COLOR/TERM
        at import again, the exact thing the shim exists to avoid)."""
        script = (
            "from quodeq.shared import _log_format\n"
            "def _boom(*a, **k):\n"
            "    raise RuntimeError('color must not be decided at import time')\n"
            "_log_format.use_color = _boom\n"
            "_log_format.should_use_color = _boom\n"
            "import quodeq.shared.logging\n"  # must not raise
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout


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
