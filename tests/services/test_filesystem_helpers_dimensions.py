"""list_available_dimensions_for_discipline must not memoise a read failure.

A bad dimensions.json (missing/corrupt) must warn through the injected
LogSink and return (), without poisoning the module-level cache -- a later
call against a fixed file must see the fixed content, not the stale ().
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.services._filesystem_helpers import (
    _read_dimensions_from_file,
    list_available_dimensions_for_discipline,
    reset_dimensions_cache,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    _read_dimensions_from_file.cache_clear()
    reset_dimensions_cache()
    yield
    _read_dimensions_from_file.cache_clear()
    reset_dimensions_cache()


def test_corrupt_dimensions_file_warns_and_returns_empty(tmp_path: Path, recording_log):
    dims_file = tmp_path / "dimensions.json"
    dims_file.write_text("{bad", encoding="utf-8")
    fake_paths = SimpleNamespace(dimensions_file=dims_file)

    result = list_available_dimensions_for_discipline(fake_paths, log=recording_log)

    assert result == ()
    assert recording_log.warning_messages


def test_failure_is_not_memoised_next_read_sees_fixed_file(tmp_path: Path, recording_log):
    dims_file = tmp_path / "dimensions.json"
    dims_file.write_text("{bad", encoding="utf-8")
    fake_paths = SimpleNamespace(dimensions_file=dims_file)

    first = list_available_dimensions_for_discipline(fake_paths, log=recording_log)
    assert first == ()

    dims_file.write_text('{"applies": [{"id": "reliability"}]}', encoding="utf-8")

    second = list_available_dimensions_for_discipline(fake_paths, log=recording_log)
    assert second == ("reliability",)
