"""config_loader delegates to the canonical shared._config singleton (no
second Config instance)."""
from __future__ import annotations

from quodeq.shared import _config, config_loader


def test_get_config_delegates_to_canonical_singleton():
    assert config_loader._get_config() is _config.get_config()


def test_get_config_override_bypasses_singleton():
    override = _config.Config()
    override.update(anthropic_api_url="https://example.invalid")
    assert config_loader._get_config(override=override) is override


def test_accessors_read_through_the_canonical_singleton():
    assert config_loader.get_anthropic_api_url() == _config.get_config()["anthropic_api_url"]
    assert config_loader.get_anthropic_api_version() == _config.get_config()["anthropic_api_version"]
    assert config_loader.get_default_host() == _config.get_config()["default_host"]


def test_accessors_take_an_injected_config_over_the_singleton():
    """#10853 — get_anthropic_api_url/version and get_default_host accept
    config= (through _lazy_constant(key, config)), resolved at call time."""
    override = _config.Config()
    override.update(
        anthropic_api_url="https://injected.invalid/url",
        anthropic_api_version="injected-version",
        default_host="injected-host",
    )
    assert config_loader.get_anthropic_api_url(config=override) == "https://injected.invalid/url"
    assert config_loader.get_anthropic_api_version(config=override) == "injected-version"
    assert config_loader.get_default_host(config=override) == "injected-host"
    # The real singleton is untouched by the injected override.
    assert config_loader.get_anthropic_api_url() == _config.get_config()["anthropic_api_url"]
