"""Provider prerequisite checks for the evaluate command.

Node/npm checks for the dev dashboard stay in ``shared/prereqs.py``; this
module owns everything that needs the provider registry.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.shared.prereqs import _SAFE_CMD_TOKEN_RE, _run_version_cmd
from quodeq.shared.utils import get_ai_cmd, get_ai_cmd_path

# Like _SAFE_CMD_TOKEN_RE but for a binary override (AI_CMD_PATH): also
# allows path separators and the Windows drive colon. Still no whitespace
# or shell metacharacters.
_SAFE_CMD_PATH_RE = re.compile(r"[A-Za-z0-9._/\\:-]+")

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

_API_CHECK_TIMEOUT_S = 5


def _is_provider_explicitly_configured() -> bool:
    """Return True if the user has explicitly set a provider via env or config."""
    return "AI_PROVIDER" in os.environ or "AI_CMD" in os.environ


def _check_cli_binary_override(provider: str, override: str) -> None:
    """Check that an AI_CMD_PATH override resolves to an executable.

    The `--version` probe is skipped here: _run_version_cmd's token charset
    forbids path separators (its Windows shell=True hardening), and for an
    explicit override the failure mode being guarded against is simply
    "binary not found".

    This is an availability check, not a security boundary: AI_CMD_PATH
    reaches this process either from the operator's own environment or via
    the dashboard API, where api._evaluation_helpers._validate_ai_cmd_path
    enforces the spawn restrictions (provider-prefixed name, on-PATH dir).
    """
    if not _SAFE_CMD_PATH_RE.fullmatch(override):
        raise RuntimeError(
            f"'{override}' is not a valid AI command override (AI_CMD_PATH).\n\n"
            f"Overrides may only contain letters, digits, '.', '_', '-', ':' "
            f"and path separators."
        )
    if shutil.which(override) is None:
        raise RuntimeError(
            f"'{override}' is set as the command override for '{provider}' "
            f"(AI_CMD_PATH) but was not found or is not executable.\n\n"
            f"Fix the override in the dashboard Settings (Advanced), or unset "
            f"AI_CMD_PATH to use '{provider}' from PATH."
        )


def _check_cli_provider(provider: str) -> None:
    """Check that a CLI provider binary is available on PATH."""
    if not _SAFE_CMD_TOKEN_RE.fullmatch(provider):
        raise RuntimeError(
            f"'{provider}' is not a valid AI provider name.\n\n"
            f"Provider names may only contain letters, digits, '.', '_', and '-'.\n\n"
            f"Choose a provider in the dashboard Settings:\n"
            f"  quodeq"
        )
    override = get_ai_cmd_path()
    if override:
        _check_cli_binary_override(provider, override)
        return
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
