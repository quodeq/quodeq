"""Tests for SA manager interface (stub)."""
from __future__ import annotations

from pathlib import Path

from quodeq.engine.sa_manager import (
    init_pending,
    get_findings,
    consume_findings,
    get_remaining,
)


def test_init_pending_is_callable(tmp_path):
    # Stub — must not raise; returns None until SA integration is implemented.
    init_pending(tmp_path / "sa.jsonl", tmp_path / "pending.jsonl")


def test_get_findings_is_callable(tmp_path):
    get_findings(tmp_path / "pending.jsonl", "src/app.ts")


def test_consume_findings_is_callable(tmp_path):
    consume_findings(tmp_path / "pending.jsonl", "src/app.ts")


def test_get_remaining_is_callable(tmp_path):
    get_remaining(tmp_path / "pending.jsonl")
