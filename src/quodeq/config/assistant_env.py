"""Environment-based configuration for the embedded assistant.

The assistant layer never reads the environment at import time; the prompt
source path is resolved here, lazily per call, and passed in.
"""
from __future__ import annotations

import os
from pathlib import Path


def assistant_context_path(env: dict[str, str] | None = None) -> Path:
    """Return the assistant system-prompt source, honoring QUODEQ_ASSISTANT_CONTEXT_PATH.

    Unset means the packaged quodeq_context.md.
    """
    default = Path(__file__).resolve().parent.parent / "data" / "assistant" / "quodeq_context.md"
    return Path((env or os.environ).get("QUODEQ_ASSISTANT_CONTEXT_PATH", str(default)))


def read_assistant_context(env: dict[str, str] | None = None) -> str:
    """Read the assistant system-prompt source, resolved lazily per call.

    Default reader for ``assistant._context.build_system_prompt``: honors the
    same ``QUODEQ_ASSISTANT_CONTEXT_PATH`` override as :func:`assistant_context_path`.
    """
    return assistant_context_path(env).read_text(encoding="utf-8")
