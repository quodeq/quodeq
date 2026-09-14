"""Tests for quodeq.shared.dim_estimates_io — the per-dim estimates sidecar.

``write_dim_estimates`` is documented as best-effort (the dashboard just
shows no estimate if the write fails), but a silent failure there should
still be observable, not dropped without a trace.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from quodeq.shared.dim_estimates_io import (
    DIM_ESTIMATES_FILENAME,
    read_dim_estimates,
    write_dim_estimates,
)


def test_write_dim_estimates_round_trips(tmp_path: Path) -> None:
    estimates = {"security": {"count": 3, "reason": "", "total": 3, "cached": 0, "excluded": 0}}
    write_dim_estimates(tmp_path, estimates)
    assert (tmp_path / DIM_ESTIMATES_FILENAME).exists()
    assert read_dim_estimates(tmp_path) == estimates


def test_write_dim_estimates_logs_on_oserror(tmp_path: Path, monkeypatch, caplog) -> None:
    """A write failure (e.g. disk full, permission denied) must be logged, not swallowed."""
    def raising_write_text(self, *args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(Path, "write_text", raising_write_text)

    with caplog.at_level(logging.WARNING):
        write_dim_estimates(tmp_path, {"security": {"count": 1}})

    assert not (tmp_path / DIM_ESTIMATES_FILENAME).exists()
    assert any(
        "write_dim_estimates" in r.message and str(tmp_path) in r.message
        for r in caplog.records
    ), f"expected a warning naming {tmp_path}, got: {[r.message for r in caplog.records]}"


def test_write_dim_estimates_logs_on_mkdir_failure(tmp_path: Path, monkeypatch, caplog) -> None:
    """mkdir failing (e.g. a parent that isn't a directory) is also caught and logged."""
    def raising_mkdir(self, *args, **kwargs):
        raise OSError("simulated permission denied")

    monkeypatch.setattr(Path, "mkdir", raising_mkdir)
    run_dir = tmp_path / "nonexistent" / "run"

    with caplog.at_level(logging.WARNING):
        write_dim_estimates(run_dir, {"security": {"count": 1}})

    assert any("write_dim_estimates" in r.message for r in caplog.records)
