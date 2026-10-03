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
        assert PROVIDERS["ollama"] == ""

    def test_openrouter_api_key_env(self):
        assert PROVIDERS["openrouter"] == "OPENROUTER_API_KEY"


def test_configure_provider_writes_the_whole_env_on_short_writes(tmp_path, monkeypatch):
    """os.write may write fewer bytes than asked; the env file still holds all of them."""
    import os
    expected = ConfigPaths.from_root(tmp_path / "full")
    expected.env_file.parent.mkdir()
    configure_provider_noninteractive("claude", expected)

    real_write = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: real_write(fd, bytes(data[:1])))
    paths = ConfigPaths.from_root(tmp_path / "short")
    paths.env_file.parent.mkdir()
    assert configure_provider_noninteractive("claude", paths) == 0
    assert paths.env_file.read_text() == expected.env_file.read_text()


def test_get_current_provider_survives_an_unreadable_env_file(tmp_path, monkeypatch):
    """An env file that exists but cannot be read (permissions, removed after
    the exists() check) falls back to the default instead of raising."""
    from pathlib import Path

    paths = ConfigPaths.from_root(tmp_path)
    paths.env_file.write_text("export AI_PROVIDER=codex\n")

    def _denied(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", _denied)
    assert get_current_provider(paths, default_provider="claude") == "claude"


def test_configure_provider_returns_1_when_the_write_fails(tmp_path, monkeypatch):
    """The contract is an int status: a disk error is 1, not a traceback."""
    from quodeq.config import ai_provider

    def _disk_full(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(ai_provider, "_write_env", _disk_full)
    assert configure_provider_noninteractive("claude", ConfigPaths.from_root(tmp_path)) == 1


def test_configure_provider_returns_1_when_gitignore_update_fails(tmp_path, monkeypatch):
    from quodeq.config import ai_provider

    def _read_only(*args, **kwargs):
        raise PermissionError("read-only file system")

    monkeypatch.setattr(ai_provider, "_ensure_gitignore", _read_only)
    assert configure_provider_noninteractive("claude", ConfigPaths.from_root(tmp_path)) == 1
