"""config_loader delegates to the canonical shared._config singleton (no
second Config instance)."""
from __future__ import annotations

from quodeq.shared import _config, config_loader


def test_get_config_delegates_to_canonical_singleton():
    assert config_loader._get_config() is _config._get_config()


def test_get_config_override_bypasses_singleton():
    override = _config.Config()
    override.update(anthropic_api_url="https://example.invalid")
    assert config_loader._get_config(override=override) is override


def test_accessors_read_through_the_canonical_singleton():
    assert config_loader.get_anthropic_api_url() == _config._get_config()["anthropic_api_url"]
    assert config_loader.get_anthropic_api_version() == _config._get_config()["anthropic_api_version"]
    assert config_loader.get_default_host() == _config._get_config()["default_host"]
