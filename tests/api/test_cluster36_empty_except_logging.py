"""Cluster 36: api best-effort handlers log at debug instead of swallowing."""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.api import _llamacpp_log_routes as llama_routes
from quodeq.api import _log_tail_helpers as log_tail_helpers
from quodeq.api import _rate_limit_file_store as store_mod
from quodeq.api import routes_project_scan
from quodeq.core.run.job_status import JobStatus
from quodeq.core.types.scan import ScanData
from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)


def test_default_log_paths_logs_when_logs_dir_cannot_be_created(monkeypatch) -> None:
    def _denied(self, *_args, **_kwargs):
        raise PermissionError(13, "read-only home")

    monkeypatch.setattr(llama_routes.Path, "mkdir", _denied)
    with patch.object(llama_routes._logger, "debug") as debug:
        paths = llama_routes._default_log_paths()
    assert paths  # the probe still yields candidates
    assert debug.called
    assert "trying the next log location" in debug.call_args.args[0]


def test_rate_limit_store_logs_temp_cleanup_failure(monkeypatch, tmp_path) -> None:
    store = store_mod.FileRateLimitStore(tmp_path / "rl.json")  # signature: (path, window=None, max_requests=None)

    def _replace_fails(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    def _unlink_fails(*_args, **_kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(store_mod.os, "replace", _replace_fails)
    monkeypatch.setattr(store_mod.os, "unlink", _unlink_fails)
    with patch.object(store_mod._logger, "warning"), patch.object(store_mod._logger, "debug") as debug:
        store._save({})  # _save(self, data: dict[str, list[float]]); the write fails soft
    assert debug.called
    assert "not removed" in debug.call_args.args[0]


def test_project_scan_logs_rescan_on_corrupt_scan_json(client, tmp_path) -> None:
    proj_dir = tmp_path / "my-proj"
    proj_dir.mkdir()
    (proj_dir / "scan.json").write_text("{not json")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (proj_dir / "repository_info.json").write_text(
        json.dumps({"location": "local", "path": str(repo_dir)})
    )
    with patch.object(routes_project_scan._logger, "debug") as debug, \
         patch("quodeq.api.routes_project_scan.scan_project", return_value=ScanData()):
        resp = client.get("/api/projects/my-proj/scan")
    assert resp.status_code == 200
    assert debug.called
    assert "rescanning" in debug.call_args.args[0]


class _ProviderStub:
    """Minimal stub providing get_log_run_dir but no in-memory _jobs table."""

    def __init__(self, run_dir):
        self._run_dir = run_dir

    def get_log_run_dir(self, job_id):
        return self._run_dir


def test_stream_terminal_state_logs_debug_on_corrupt_status_json(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "status.json").write_text("[")
    provider = _ProviderStub(run_dir)
    with patch.object(log_tail_helpers._logger, "debug") as debug:
        state = log_tail_helpers._stream_terminal_state(provider, "job-123")
    assert state == JobStatus.DONE
    assert debug.called
    assert debug.call_args.args[1] == "job-123"
