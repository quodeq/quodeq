"""Tests for SA manager interface (stub — raises NotImplementedError)."""
from __future__ import annotations

import pytest

from quodeq.engine.sa_manager import (
    init_pending,
    get_findings,
    consume_findings,
    get_remaining,
)


def test_init_pending_raises(tmp_path):
    with pytest.raises(NotImplementedError, match="SA integration"):
        init_pending(tmp_path / "sa.jsonl", tmp_path / "pending.jsonl")


def test_get_findings_raises(tmp_path):
    with pytest.raises(NotImplementedError, match="SA integration"):
        get_findings(tmp_path / "pending.jsonl", "src/app.ts")


def test_consume_findings_raises(tmp_path):
    with pytest.raises(NotImplementedError, match="SA integration"):
        consume_findings(tmp_path / "pending.jsonl", "src/app.ts")


def test_get_remaining_raises(tmp_path):
    with pytest.raises(NotImplementedError, match="SA integration"):
        get_remaining(tmp_path / "pending.jsonl")
