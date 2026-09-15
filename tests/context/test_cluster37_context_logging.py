"""Cluster 37: context best-effort handlers log at debug."""
from __future__ import annotations

from pathlib import Path

from unittest.mock import patch

from quodeq.context import online_cache
from quodeq.context.precedent import MARKER_NAME, PrecedentCorpus


def test_touch_logs_missing_path(tmp_path) -> None:
    with patch.object(online_cache._logger, "debug") as debug:
        online_cache._touch(tmp_path / "missing")
    assert debug.called
    assert "cache touch failed" in debug.call_args.args[0]


def test_trip_logs_when_marker_cannot_be_written(tmp_path: Path) -> None:
    corpus = PrecedentCorpus(
        vectors=[],
        embed=lambda batch, **kwargs: [],
        threshold=0.85,
        marker_path=tmp_path / "missing-dir" / MARKER_NAME,
    )
    from quodeq.context import precedent_corpus

    with patch.object(precedent_corpus._logger, "warning") as warning, \
            patch.object(precedent_corpus._logger, "debug") as debug:
        corpus._trip("test")
    assert warning.called  # the existing warning call stays
    assert debug.called
    assert "not written" in debug.call_args.args[0]
