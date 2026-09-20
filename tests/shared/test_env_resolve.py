"""The one config-layer fallback every injectable env seam routes through."""
from __future__ import annotations

import os

from quodeq.shared._env_resolve import resolve_env, resolve_env_mut


class TestResolveEnv:
    def test_injected_mapping_is_returned_unchanged(self):
        injected = {"VAR": "value"}
        assert resolve_env(injected) is injected

    def test_injected_empty_mapping_means_no_variables_set(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        assert resolve_env({}).get("VAR") is None

    def test_none_falls_back_to_the_process_environment(self):
        assert resolve_env(None) is os.environ
        assert resolve_env() is os.environ


class TestResolveEnvMut:
    def test_injected_mapping_is_written_through(self):
        injected: dict[str, str] = {}
        resolve_env_mut(injected)["PATH"] = "x"
        assert injected == {"PATH": "x"}

    def test_injected_empty_mapping_means_no_variables_set(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        assert resolve_env_mut({}).get("VAR") is None

    def test_none_falls_back_to_the_process_environment(self):
        assert resolve_env_mut(None) is os.environ
