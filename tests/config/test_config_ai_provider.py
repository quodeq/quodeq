from quodeq.config.ai_provider import configure_provider_noninteractive
from quodeq.config.ai_provider import get_current_provider
from quodeq.config.ai_provider import PROVIDERS
from quodeq.config.paths import ConfigPaths


def test_configure_provider_writes_env(tmp_path):
    """configure_provider_noninteractive('claude') should write a valid .quodeq.env file."""
    paths = ConfigPaths.from_root(tmp_path)
    exit_code = configure_provider_noninteractive("claude", paths)
    assert exit_code == 0
    assert paths.env_file.read_text().strip().startswith("# Quodeq provider config")
    assert "AI_PROVIDER=claude" in paths.env_file.read_text()


def test_configure_provider_works_without_fchmod(tmp_path, monkeypatch):
    """os.fchmod is absent on Windows; saving provider config must still
    succeed there (the post-replace os.chmod carries the 0600 guarantee)."""
    import os
    monkeypatch.delattr(os, "fchmod", raising=False)
    paths = ConfigPaths.from_root(tmp_path)
    exit_code = configure_provider_noninteractive("claude", paths)
    assert exit_code == 0
    assert paths.env_file.exists()
    assert "AI_PROVIDER=claude" in paths.env_file.read_text()


def test_get_current_provider_prefers_env_file(tmp_path):
    env_file = tmp_path / ".quodeq.env"
    env_file.write_text("export AI_PROVIDER=codex\n")
    paths = ConfigPaths.from_root(tmp_path)
    assert get_current_provider(paths) == "codex"


def test_get_current_provider_returns_default_when_no_env(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    result = get_current_provider(paths)
    assert result is not None  # falls back to default provider
    assert isinstance(result, str) and len(result) > 0


def test_configure_unknown_provider(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    exit_code = configure_provider_noninteractive("nonexistent_provider", paths)
    assert exit_code != 0


class TestExpandedProviders:
    """PROVIDERS dict should include API-mode providers."""

    def test_ollama_in_providers(self):
        assert "ollama" in PROVIDERS

    def test_openrouter_in_providers(self):
        assert "openrouter" in PROVIDERS

    def test_custom_in_providers(self):
        assert "custom" in PROVIDERS

    def test_ollama_no_api_key_required(self):
        api_key_var, cmd = PROVIDERS["ollama"]
        assert api_key_var == ""

    def test_openrouter_api_key_env(self):
        api_key_var, cmd = PROVIDERS["openrouter"]
        assert api_key_var == "OPENROUTER_API_KEY"
