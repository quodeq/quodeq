"""``FilesystemActionProvider.get_accumulated`` threads a real sink all the
way down to the accumulated walk's per-run read failures.

Full production path, no ``log=`` override anywhere on the caller side:
``FilesystemActionProvider.get_accumulated`` -> ``fs_reports.get_accumulated``
-> ``compute_accumulated`` -> the slim classification walk's
``_read_run_data_safely``. Proves the ``log=SHARED_LOG`` wiring added at
every hop between them actually reaches a real sink in production, not just
the mechanism when a test hands ``log=`` in directly -- the gap
``test_score_cache_write_failure_logging.py::TestProductionCallerReachesRealSink``
exists to close for the score-cache read-through path; this is the same
check for the ``/api/projects/<project>/accumulated`` route.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.filesystem import FilesystemActionProvider


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class _FakeLog:
    def __init__(self):
        self.warnings: list[str] = []

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def debug(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        pass


def test_get_accumulated_logs_a_real_run_read_failure_through_shared_log(
    tmp_path: Path, monkeypatch,
) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "proj" / "20260101" / "evaluation" / "security.json",
        {"dimension": "security", "overallScore": "8/10", "overallGrade": "Good",
         "filesRead": 3},
    )
    (reports / "proj" / "20260101" / "evidence").mkdir(parents=True, exist_ok=True)
    (reports / "proj" / "20260101" / "evidence" / "manifest.json").write_text("{}")
    (reports / "proj" / "20260101" / "scan.json").write_text("{}")

    def _flaky(reports_root, project, run_id):
        raise ValueError("corrupt eval file")

    monkeypatch.setattr("quodeq.services._accumulated_data.read_run_data", _flaky)

    fake_log = _FakeLog()
    # Patch the name filesystem.py resolves at call time, not the log_sink
    # module's copy -- proves the import-and-thread wiring in that file
    # reaches a real sink.
    monkeypatch.setattr("quodeq.services.filesystem.SHARED_LOG", fake_log)

    provider = FilesystemActionProvider()
    payload = provider.get_accumulated(str(reports), "proj", None)

    # Fail-open: the run's read failure degrades that run out of the
    # accumulated view instead of raising through the API route.
    assert payload is not None
    assert any("read_run_data failed" in msg and "20260101" in msg for msg in fake_log.warnings)
