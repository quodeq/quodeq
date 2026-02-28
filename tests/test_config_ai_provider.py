from codecompass.config.ai_provider import configure_provider_noninteractive
from codecompass.config.ai_provider import get_current_provider
from codecompass.config.paths import ConfigPaths


def test_configure_provider_writes_env(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    exit_code = configure_provider_noninteractive("claude", paths)
    assert exit_code == 0
    assert paths.env_file.read_text().strip().startswith("# CodeCompass provider config")
    assert "AI_PROVIDER=claude" in paths.env_file.read_text()


def test_get_current_provider_prefers_env_file(tmp_path):
    env_file = tmp_path / ".codecompass.env"
    env_file.write_text("export AI_PROVIDER=codex\n")
    paths = ConfigPaths.from_root(tmp_path)
    assert get_current_provider(paths) == "codex"
