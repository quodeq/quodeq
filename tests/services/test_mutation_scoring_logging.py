"""_resolve_default_run_id must not swallow a list_runs failure silently."""
from __future__ import annotations

import logging
from unittest.mock import patch

from quodeq.services._mutation_scoring import _resolve_default_run_id


def test_resolve_default_run_id_logs_list_runs_failure(caplog, tmp_path):
    with patch(
        "quodeq.services._mutation_scoring.list_runs",
        side_effect=RuntimeError("disk unavailable"),
    ), caplog.at_level(logging.WARNING):
        result = _resolve_default_run_id(str(tmp_path), "proj-1")
    assert result is None
    assert any("proj-1" in r.message for r in caplog.records)
