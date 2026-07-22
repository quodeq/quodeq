"""Security-related text sanitization helpers."""
from __future__ import annotations

import re

SENSITIVE_PATTERNS = re.compile(
    # The optional quote after the keyword catches JSON-shaped credentials
    # such as `"token": "abc"`; the [=:\s]+ separator keeps the existing
    # `token=abc` / `token: abc` / `token abc` forms matching.
    r"(api[_-]?key|token|secret|password|authorization)[\"']?[=:\s]+\S+",
    re.IGNORECASE,
)
"""Compiled regex for detecting secrets in log/error output."""


def sanitize_sensitive(text: str) -> str:
    """Mask potential secrets in *text* for safe logging/display."""
    return SENSITIVE_PATTERNS.sub(r"\1=***", text)
