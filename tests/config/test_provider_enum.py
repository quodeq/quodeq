"""PROVIDERS keyed by the Provider enum, values being the API-key env var names."""
from quodeq.config.provider import PROVIDERS, Provider


def test_providers_keyed_by_enum():
    assert set(PROVIDERS) == set(Provider)
    assert PROVIDERS[Provider.CLAUDE] == "ANTHROPIC_API_KEY"
    assert PROVIDERS[Provider.COPILOT] == ""


def test_provider_values_are_the_cli_names():
    assert Provider.COPILOT == "copilot"
    assert Provider("llamacpp") is Provider.LLAMACPP


def test_plain_strings_still_look_up():
    # Callers pass raw request strings; StrEnum keys hash as their value.
    assert "claude" in PROVIDERS
    assert PROVIDERS.get("bogus") is None


def test_config_reexports_the_core_provider():
    from quodeq.core.types.provider import Provider as CoreProvider

    assert Provider is CoreProvider


def test_omlx_is_local_but_not_a_provider_member():
    from quodeq.llm_bridge import LOCAL_PROVIDERS

    assert "omlx" not in Provider
    assert LOCAL_PROVIDERS == {"ollama", "llamacpp", "omlx"}
