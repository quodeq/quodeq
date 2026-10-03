"""Dedicated Copilot CLI profile shared by evaluations and assistant turns."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from quodeq.shared.json_state import dump_json_and_replace

_PROFILE_LOCK = threading.Lock()
_ALLOWED_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM", "TMPDIR", "TZ",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "SystemRoot",
    "WINDIR", "PATHEXT", "TEMP", "TMP",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR",
})
_OWNER_RW = 0o600  # Only the profile owner may modify its execution settings.
_OWNER_RWX = 0o700  # Login state and sessions must not be visible to other users.


def _prepare_profile(profile: Path) -> None:
    profile.mkdir(parents=True, exist_ok=True, mode=_OWNER_RWX)
    profile.chmod(_OWNER_RWX)
    # config.json belongs to the CLI and may contain JSONC/auth metadata.
    config_path = profile / "settings.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        if not isinstance(config, dict):
            raise ValueError("expected a JSON object")
        mcp_path = profile / "mcp-config.json"
        if mcp_path.exists():
            mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
            if not isinstance(mcp, dict) or mcp.get("mcpServers"):
                raise ValueError("the dedicated profile must not contain custom MCP servers")
        plugins = profile / "installed-plugins"
        if plugins.is_dir() and any(plugins.iterdir()):
            raise ValueError("the dedicated profile must not contain plugins")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot use Quodeq's Copilot profile at {profile}: {exc}") from exc
    ide = config.get("ide")
    if config.get("disableAllHooks") is True and isinstance(ide, dict) and ide.get("autoConnect") is False:
        config_path.chmod(_OWNER_RW)
        return
    config["disableAllHooks"] = True
    config["ide"] = {**(ide if isinstance(ide, dict) else {}), "autoConnect": False}
    fd, name = tempfile.mkstemp(dir=profile, suffix=".json")
    try:
        dump_json_and_replace(fd, name, config_path, config, mode=_OWNER_RW)
    finally:
        Path(name).unlink(missing_ok=True)


def build_copilot_env(env: dict[str, str]) -> dict[str, str]:
    """Use Quodeq's login profile, ignoring inherited auth, BYOK and permission overrides."""
    home = env.get("HOME") or env.get("USERPROFILE")
    profile = (Path(home) if home else Path.home()) / ".quodeq" / "copilot"
    with _PROFILE_LOCK:
        _prepare_profile(profile)
    result = {
        key: value for key, value in env.items()
        if key in _ALLOWED_ENV_KEYS or key.startswith("LC_")
    }
    result["COPILOT_HOME"] = str(profile)
    return result
