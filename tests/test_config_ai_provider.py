from quodeq.config.ai_provider import configure_provider_noninteractive
from quodeq.config.ai_provider import get_current_provider
from quodeq.config.paths import ConfigPaths


def test_configure_provider_writes_env(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    exit_code = configure_provider_noninteractive("claude", paths)
    assert exit_code == 0
    assert paths.env_file.read_text().strip().startswith("# Quodeq provider config")
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


def test_configure_unknown_provider(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    exit_code = configure_provider_noninteractive("nonexistent_provider", paths)
    assert exit_code != 0
