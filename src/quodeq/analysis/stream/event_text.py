"""Shared text extraction from stream-json events.

The implementation moved inward to ``core/stream/events.py`` (pure
wire-format parsing, reachable from services without a services ->
analysis arrow). This module stays as the analysis-side name.
"""
from __future__ import annotations

from quodeq.core.stream.events import (  # noqa: F401 — re-exported API
    TEXT_EXTRACTORS,
    texts_from_assistant,
    texts_from_item_completed,
    texts_from_result,
)
