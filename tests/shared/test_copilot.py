import json
import os
from pathlib import Path

import pytest

from quodeq.assistant.adapters._cli_spawn import build_chat_env
from quodeq.shared.copilot import build_copilot_env


def test_profile_preserves_login_settings_and_disables_hooks(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    profile = tmp_path / ".quodeq/copilot"
    profile.mkdir(parents=True)
    login = profile / "config.json"
    login.write_text('// Managed by Copilot\n{"firstLaunchAt": "test"}')
    config = profile / "settings.json"
    config.write_text(json.dumps({"disableAllHooks": True, "ide": None}))
    env = build_copilot_env({"PATH": "/bin"})
    settings = json.loads(config.read_text())
    assert login.read_text() == '// Managed by Copilot\n{"firstLaunchAt": "test"}'
    assert settings["disableAllHooks"] is True
    assert settings["ide"]["autoConnect"] is False
    assert env["COPILOT_HOME"] == str(profile)
    before = config.stat().st_mtime_ns
    build_copilot_env({})
    assert config.stat().st_mtime_ns == before


@pytest.mark.parametrize("content", ["not-json", "[]", "null"])
def test_invalid_profile_fails_explicitly_without_overwriting(tmp_path, monkeypatch, content):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    profile = tmp_path / ".quodeq/copilot"
    profile.mkdir(parents=True)
    config = profile / "settings.json"
    config.write_text(content)
    with pytest.raises(RuntimeError, match="Copilot profile"):
        build_copilot_env({})
    assert config.read_text() == content


def test_dedicated_profile_rejects_unrelated_mcp_servers(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    profile = tmp_path / ".quodeq/copilot"
    profile.mkdir(parents=True)
    (profile / "mcp-config.json").write_text(json.dumps({"mcpServers": {"company": {}}}))
    with pytest.raises(RuntimeError, match="must not contain custom MCP servers"):
        build_copilot_env({})


@pytest.mark.parametrize("content", ["not-json", "[]", "null"])
def test_invalid_mcp_profile_fails_explicitly_without_overwriting(tmp_path, content):
    profile = tmp_path / ".quodeq/copilot"
    profile.mkdir(parents=True)
    config = profile / "mcp-config.json"
    config.write_text(content)
    with pytest.raises(RuntimeError, match="Copilot profile"):
        build_copilot_env({"HOME": str(tmp_path)})
    assert config.read_text() == content


def test_dedicated_profile_rejects_plugins(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    plugins = tmp_path / ".quodeq/copilot/installed-plugins"
    plugins.mkdir(parents=True)
    (plugins / "plugin.json").write_text("{}")
    with pytest.raises(RuntimeError, match="must not contain plugins"):
        build_copilot_env({})


def test_copilot_chat_env_preserves_corporate_connectivity_not_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    env = build_chat_env({
        "PATH": "/bin", "HTTPS_PROXY": "http://proxy.invalid",
        "NODE_EXTRA_CA_CERTS": "/corp/ca.pem", "GH_TOKEN": "not-inherited",
        "COPILOT_PROVIDER_BASE_URL": "http://not-copilot",
        "AWS_SECRET_ACCESS_KEY": "not-inherited",
    }, provider="copilot")
    assert env["HTTPS_PROXY"] == "http://proxy.invalid"
    assert env["NODE_EXTRA_CA_CERTS"] == "/corp/ca.pem"
    assert env["COPILOT_HOME"] == str(tmp_path / ".quodeq/copilot")
    assert not {"GH_TOKEN", "COPILOT_PROVIDER_BASE_URL", "AWS_SECRET_ACCESS_KEY"} & env.keys()


def test_profile_preserves_unrelated_ide_settings(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    profile = tmp_path / ".quodeq/copilot"
    profile.mkdir(parents=True)
    settings = profile / "settings.json"
    settings.write_text(json.dumps({"ide": {"autoConnect": True, "openDiffOnEdit": False}}))
    build_copilot_env({})
    assert json.loads(settings.read_text())["ide"] == {
        "autoConnect": False, "openDiffOnEdit": False,
    }


@pytest.mark.parametrize("home_key", ["HOME", "USERPROFILE"])
def test_profile_home_is_injectable_and_unrelated_secrets_are_not_inherited(tmp_path, monkeypatch, home_key):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "default")
    env = build_copilot_env({
        home_key: str(tmp_path), "PATH": "/bin",
        "ANTHROPIC_API_KEY": "not-inherited", "AWS_SECRET_ACCESS_KEY": "not-inherited",
        "APPDATA": "platform-data", "SYSTEMROOT": "platform-system",
    })
    assert env["COPILOT_HOME"] == str(tmp_path / ".quodeq/copilot")
    assert env["APPDATA"] == "platform-data"
    assert env["SYSTEMROOT"] == "platform-system"
    assert not {"ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY"} & env.keys()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_profile_repairs_permissive_directory_and_settings_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    profile = tmp_path / ".quodeq/copilot"
    profile.mkdir(parents=True)
    profile.chmod(0o755)
    settings = profile / "settings.json"
    settings.write_text('{"disableAllHooks":true,"ide":{"autoConnect":false}}')
    settings.chmod(0o644)
    build_copilot_env({})
    assert profile.stat().st_mode & 0o777 == 0o700
    assert settings.stat().st_mode & 0o777 == 0o600
