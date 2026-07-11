"""Prerequisite checks for external tool dependencies."""
from __future__ import annotations

import os
import re
import subprocess
import urllib.error
import urllib.request

from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.shared.utils import IS_WIN32 as _IS_WIN32, get_ai_cmd

_INSTALL_HINT_NODE = (
    "Install Node.js + npm from https://nodejs.org/ or via your package manager:\n"
    "  brew install node                    # macOS (installs both)\n"
    "  sudo apt install -y nodejs npm       # Ubuntu/Debian (two packages)\n"
    "  sudo dnf install -y nodejs npm       # Fedora/RHEL\n"
    "  pacman -S nodejs npm                 # Arch"
)

_CLI_INSTALL_HINTS: dict[str, str] = {
    "claude": (
        "Install Claude Code:\n"
        "  npm install -g @anthropic-ai/claude-code\n"
        "  https://docs.anthropic.com/en/docs/claude-code/overview"
    ),
    "codex": (
        "Install Codex CLI:\n"
        "  npm install -g @openai/codex\n"
        "  https://developers.openai.com/codex/quickstart"
    ),
    "gemini": (
        "Install Gemini CLI:\n"
        "  npm install -g @google/gemini-cli\n"
        "  https://geminicli.com/docs/get-started/installation/"
    ),
}

_SETTINGS_HINT = (
    "Open the dashboard and go to Settings to select your AI provider:\n"
    "  quodeq"
)

_VERSION_CMD_TIMEOUT_S = 30
_API_CHECK_TIMEOUT_S = 5

# Provider/command tokens are restricted to a charset with no shell
# metacharacters, so even on the Windows shell=True path (needed for npm
# .cmd shim resolution) a value like "x & calc.exe" can never reach cmd.exe.
_SAFE_CMD_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]+")


def _run_version_cmd(cmd: list[str]) -> str:
    """Run a version command and return its stdout, or raise.

    On Windows ``shell=True`` is required so npm-installed ``.cmd`` shims
    resolve on PATH. To keep that shell safe, every token in *cmd* is
    validated against a strict ``[A-Za-z0-9._-]`` charset, so no shell
    metacharacter (space, ``&``, ``|``, ``>`` ...) can reach ``cmd.exe``.
    Callers that accept external input (e.g. a provider name from the
    ``AI_CMD`` env var) must still validate at their own layer; this is
    defense in depth.
    """
    if not isinstance(cmd, list):
        raise TypeError("cmd must be a list of strings, not a raw string")
    for token in cmd:
        if not isinstance(token, str) or not _SAFE_CMD_TOKEN_RE.fullmatch(token):
            raise ValueError(f"unsafe command token: {token!r}")
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=True, shell=_IS_WIN32,
        timeout=_VERSION_CMD_TIMEOUT_S,
    )
    return result.stdout.strip()


def _parse_major(version_str: str) -> int:
    """Extract the major version number from a version string like 'v20.11.0' or '10.2.0'."""
    cleaned = version_str.lstrip("v")
    return int(cleaned.split(".")[0])


def _check_tool_version(cmd: list[str], tool_name: str, min_major: int, install_hint: str) -> None:
    """Raise RuntimeError if *tool_name* is missing or below *min_major*."""
    try:
        version_str = _run_version_cmd(cmd)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"{tool_name} {min_major}+ is required but not found.\n{install_hint}"
        ) from exc
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return
    if major < min_major:
        raise RuntimeError(
            f"{tool_name} {version_str} is below the minimum required version {min_major}.x.\n"
            f"{install_hint}"
        )


def check_node(min_major: int = 20) -> None:
    """Raise RuntimeError if Node.js is missing or below minimum version."""
    _check_tool_version(["node", "--version"], "Node.js", min_major, _INSTALL_HINT_NODE)


def check_npm(min_major: int = 10) -> None:
    """Raise RuntimeError if npm is missing or below minimum version."""
    _check_tool_version(["npm", "--version"], "npm", min_major, _INSTALL_HINT_NODE)


def _is_provider_explicitly_configured() -> bool:
    """Return True if the user has explicitly set a provider via env or config."""
    return "AI_PROVIDER" in os.environ or "AI_CMD" in os.environ


def _check_cli_provider(provider: str) -> None:
    """Check that a CLI provider binary is available on PATH."""
    if not _SAFE_CMD_TOKEN_RE.fullmatch(provider):
        raise RuntimeError(
            f"'{provider}' is not a valid AI provider name.\n\n"
            f"Provider names may only contain letters, digits, '.', '_', and '-'.\n\n"
            f"Choose a provider in the dashboard Settings:\n"
            f"  quodeq"
        )
    try:
        _run_version_cmd([provider, "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        hint = _CLI_INSTALL_HINTS.get(provider, f"Install {provider} and make sure it is on your PATH.")
        raise RuntimeError(
            f"'{provider}' is configured as your AI provider but was not found.\n\n"
            f"{hint}\n\n"
            f"Or choose a different provider in the dashboard Settings:\n"
            f"  quodeq"
        ) from exc


def _check_api_provider(provider: str, *, env: dict[str, str] | None = None) -> None:
    """Check that an API provider has basic connectivity (Ollama: server running)
    and that cloud providers have their required API key set."""
    _env = os.environ if env is None else env
    if provider == "ollama":
        try:
            _ollama_base = _env.get("OLLAMA_BASE_URL", "http://localhost:11434")
            with urllib.request.urlopen(f"{_ollama_base}/api/tags", timeout=_API_CHECK_TIMEOUT_S):
                pass
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(
                "Ollama is configured as your AI provider but the server is not running.\n\n"
                "Start it with:\n"
                "  ollama serve\n\n"
                "Or install Ollama from https://ollama.com/download"
            ) from exc
    elif provider == "llamacpp":
        try:
            _base = _env.get("LLAMACPP_BASE_URL", "http://localhost:8080")
            with urllib.request.urlopen(f"{_base}/health", timeout=_API_CHECK_TIMEOUT_S):
                pass
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(
                "llama.cpp is configured as your AI provider but llama-server is not running.\n\n"
                "Start it with a GGUF model, for example:\n"
                "  llama-server -m path/to/model.gguf --port 8080\n\n"
                "For speculative decoding (MTP), pair it with a draft model:\n"
                "  llama-server -m path/to/target.gguf -md path/to/drafter.gguf --port 8080\n\n"
                "Install llama.cpp from https://github.com/ggml-org/llama.cpp"
            ) from exc
    else:
        # Cloud API providers (openrouter, ...): fail fast on a missing key
        # instead of surfacing 401s mid-evaluation.
        provider_cfg = get_provider_configs().get(provider, {})
        key_env = provider_cfg.get("api_key_env", "")
        if provider_cfg.get("api_key_required") and key_env and not _env.get(key_env):
            browse_url = provider_cfg.get("browse_url", "")
            url_hint = f"  {browse_url}\n\n" if browse_url else ""
            raise RuntimeError(
                f"'{provider}' is configured as your AI provider but the "
                f"{key_env} environment variable is not set.\n\n"
                f"Create an API key and export it:\n"
                f"  export {key_env}=<your-key>\n\n"
                f"{url_hint}{_SETTINGS_HINT}"
            )


def _collect_tool_issue(cmd: list[str], tool_name: str, min_major: int) -> str | None:
    """Return a one-line description of a tool problem, or None if OK.

    Used by aggregators that want to report every missing/outdated tool in
    a single error instead of failing fast on the first one.
    """
    try:
        version_str = _run_version_cmd(cmd)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return f"{tool_name} {min_major}+ not found on PATH"
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return None
    if major < min_major:
        return f"{tool_name} {version_str} is below the minimum required version {min_major}.x"
    return None


def check_dashboard_dev_prereqs() -> None:
    """Check Node.js and npm prerequisites for `quodeq dashboard --dev`.

    Production dashboards ship a pre-built UI inside the wheel and do not
    require Node or npm at runtime. This check is only relevant when
    running with `--dev`, which rebuilds the UI from source on the user's
    machine.

    Runs every tool check, collects any issues, and raises a single
    RuntimeError listing them all, so a contributor missing both Node and
    npm (common on fresh Debian/Ubuntu systems where they ship as separate
    packages) gets the full story in one message with one install command.
    """
    issues: list[str] = []
    node_issue = _collect_tool_issue(["node", "--version"], "Node.js", 20)
    if node_issue is not None:
        issues.append(node_issue)
    npm_issue = _collect_tool_issue(["npm", "--version"], "npm", 10)
    if npm_issue is not None:
        issues.append(npm_issue)
    if not issues:
        return
    bullets = "\n".join(f"  - {issue}" for issue in issues)
    raise RuntimeError(
        f"Missing or outdated prerequisites:\n{bullets}\n\n{_INSTALL_HINT_NODE}"
    )


def check_evaluate_prereqs() -> None:
    """Check all prerequisites for the evaluate command.

    Checks the configured AI provider instead of always assuming Claude.
    If no provider is configured, tells the user to select one.
    """
    if not _is_provider_explicitly_configured():
        raise RuntimeError(
            "No AI provider configured.\n\n"
            "Quodeq needs an AI provider to evaluate your code. You can use:\n\n"
            "  Local (free, private):  Ollama with Gemma 4\n"
            "  Cloud (faster):         Claude Code, Codex CLI, or Gemini CLI\n\n"
            f"{_SETTINGS_HINT}"
        )

    provider = get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(provider, {})
    provider_type = provider_cfg.get("type", "cli")

    if provider_type == "cli":
        _check_cli_provider(provider)
    elif provider_type == "api":
        _check_api_provider(provider)
