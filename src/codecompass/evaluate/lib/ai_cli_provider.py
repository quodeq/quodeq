from __future__ import annotations

import os


def get_ai_cmd() -> str:
    return os.environ.get("AI_CMD", "claude")


def get_ai_model() -> str | None:
    return os.environ.get("AI_MODEL") or None
