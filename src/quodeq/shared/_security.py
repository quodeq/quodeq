"""Security-related text sanitization helpers."""
from __future__ import annotations

import re

SENSITIVE_PATTERNS = re.compile(
    r"(api[_-]?key|token|secret|password|authorization)[=:\s]+\S+",
    re.IGNORECASE,
)
"""Compiled regex for detecting secrets in log/error output."""


def sanitize_sensitive(text: str) -> str:
    """Mask potential secrets in *text* for safe logging/display."""
    return SENSITIVE_PATTERNS.sub(r"\1=***", text)
