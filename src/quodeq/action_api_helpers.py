"""Shared helpers for action API modules."""
from __future__ import annotations

from typing import Any


def _error(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    return {"error": message, "code": code}, status
