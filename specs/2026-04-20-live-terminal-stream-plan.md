# Live Terminal Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream every evaluation's live terminal output to the dashboard via SSE, backed by a per-run `run.log` file, and render it with xterm.js inline under the existing status card.

**Architecture:** Producers (CLI and dashboard-spawned subprocess) append stderr lines verbatim to `{run_dir}/run.log`. A new Flask SSE endpoint tails that file and pushes lines to the dashboard via `EventSource`. The UI mounts an xterm.js terminal below the status card; it replays history from offset 0 then tails live until the server sends `event: done`.

**Tech Stack:** Python 3.12 (Flask, stdlib logging), React 18 + Vite 7 (xterm.js v5, xterm-addon-fit), pytest 9.

See spec: [2026-04-20-live-terminal-stream-design.md](2026-04-20-live-terminal-stream-design.md).

---

## File Structure

**New files**
- `src/quodeq/shared/run_log.py` — `RunLogWriter` (plain file wrapper) + `RunLogHandler` (logging.Handler adapter). One responsibility: append lines to run.log.
- `src/quodeq/api/_log_stream_routes.py` — SSE + plain JSON endpoints. One responsibility: serve the log file to dashboards.
- `src/quodeq/ui/src/features/evaluation/components/LiveTerminal.jsx` — xterm.js renderer + EventSource wiring. One responsibility: live-render the log stream.
- `tests/shared/test_run_log.py`
- `tests/api/test_log_stream_routes.py`
- `tests/services/test_jobs_run_log.py`
- `tests/ci/test_run_log_integration.py`

**Modified files**
- `src/quodeq/_cli_evaluation.py` — convert inline `print(..., file=sys.stderr)` calls to `log_info(...)`; install `RunLogHandler` on the `quodeq` logger in the try/finally of `_run_pipeline_with_cleanup`.
- `src/quodeq/services/jobs.py` — `_consume_stream` tees each line to a `RunLogWriter` bound to the job's run_dir.
- `src/quodeq/api/routes_registry.py` — register the new log-stream routes.
- `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx` — render `<LiveTerminal>` after `<ConsolePanel>`.
- `src/quodeq/ui/package.json` — add `xterm` and `xterm-addon-fit`.

---

## Task 1: RunLogWriter + RunLogHandler utility

**Files:**
- Create: `src/quodeq/shared/run_log.py`
- Test: `tests/shared/test_run_log.py`

- [ ] **Step 1: Write failing tests**

Create `tests/shared/__init__.py` (empty) if it doesn't already exist, then write:

```python
# tests/shared/test_run_log.py
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.shared.run_log import RunLogWriter, RunLogHandler


def test_write_creates_file_with_line(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    writer.write("hello")
    writer.close()
    assert (tmp_path / "run.log").read_text() == "hello\n"


def test_write_preserves_existing_newline(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    writer.write("already-newlined\n")
    writer.close()
    assert (tmp_path / "run.log").read_text() == "already-newlined\n"


def test_write_is_line_buffered(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    writer.write("first")
    # Read back without closing — flush should have happened.
    assert (tmp_path / "run.log").read_text() == "first\n"
    writer.close()


def test_silent_on_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    writer = RunLogWriter(missing)  # must not raise
    writer.write("ignored")  # must not raise
    writer.close()
    assert not (missing / "run.log").exists()


def test_path_property(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    assert writer.path == tmp_path / "run.log"
    writer.close()


def test_handler_forwards_log_record(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test.run_log.1")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("message-a")
    logger.removeHandler(handler)
    writer.close()
    assert (tmp_path / "run.log").read_text() == "message-a\n"


def test_handler_never_raises_on_format_error(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    handler = RunLogHandler(writer)
    logger = logging.getLogger("test.run_log.2")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # %d on a string arg — format-time error, must not propagate.
    logger.info("%d", "not-an-int")
    logger.removeHandler(handler)
    writer.close()
```

- [ ] **Step 2: Run tests, confirm failure**

```
cd /Users/victor/GitHub/quodeq/.claude/worktrees/elegant-goldberg-396ca4
uv run pytest tests/shared/test_run_log.py -v
```
Expected: `ImportError: cannot import name 'RunLogWriter' from 'quodeq.shared.run_log'`.

- [ ] **Step 3: Implement the module**

```python
# src/quodeq/shared/run_log.py
"""Per-run log file writer.

Appends the evaluation's stderr-stream verbatim to ``{run_dir}/run.log``.
Used by both the CLI pipeline and the dashboard subprocess dispatcher.

Failures are silent-by-design: this file is diagnostic, never load-bearing.
A disk-full or permission error must not abort an evaluation.
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import IO

_LOG_FILENAME = "run.log"


class RunLogWriter:
    """Thread-safe append-only writer for a per-run log file."""

    def __init__(self, run_dir: Path) -> None:
        self._path = run_dir / _LOG_FILENAME
        self._fh: IO[str] | None = None
        self._lock = threading.Lock()
        self._disabled = False
        try:
            self._fh = open(self._path, "a", buffering=1, encoding="utf-8")
        except OSError as exc:
            print(f"run_log: could not open {self._path}: {exc}", file=sys.stderr)
            self._disabled = True

    @property
    def path(self) -> Path:
        return self._path

    def write(self, line: str) -> None:
        """Append *line* to run.log. Adds a trailing newline if missing."""
        if self._disabled or self._fh is None:
            return
        text = line if line.endswith("\n") else line + "\n"
        with self._lock:
            try:
                self._fh.write(text)
                self._fh.flush()
            except OSError:
                self._disabled = True

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                finally:
                    self._fh = None


class RunLogHandler(logging.Handler):
    """logging.Handler that forwards formatted records to a RunLogWriter."""

    def __init__(self, writer: RunLogWriter) -> None:
        super().__init__()
        self._writer = writer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._writer.write(self.format(record))
        except Exception:
            # Logging must never crash the app.
            pass
```

- [ ] **Step 4: Run tests, confirm pass**

```
uv run pytest tests/shared/test_run_log.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/shared/run_log.py tests/shared/
git commit -m "feat(run-log): add RunLogWriter and RunLogHandler utility"
```

---

## Task 2: Convert inline stderr prints in _cli_evaluation.py to log_info

**Files:**
- Modify: `src/quodeq/_cli_evaluation.py` (lines 118, 124, 126, 128, 130, 131, 155, 162, 197)

The CLI uses a mix of `log_info()` (flows through the `quodeq` logger) and direct `print(..., file=sys.stderr)`. Only the former will be captured by a `RunLogHandler`. Convert the direct prints so every progress message flows through the logger.

- [ ] **Step 1: Write failing test**

```python
# tests/ci/test_cli_uses_log_info.py
from __future__ import annotations

import ast
from pathlib import Path


def test_no_direct_stderr_prints_in_pipeline() -> None:
    """The CLI pipeline must route progress messages through log_info, not print(..., file=sys.stderr).

    Allowed exceptions: dimension score lines in _execute_pipeline's success branch
    (line 133: `print(f"  {dim}: {score}")`) because those print to stdout for
    shell piping.
    """
    src = Path("src/quodeq/_cli_evaluation.py").read_text()
    tree = ast.parse(src)
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            for kw in node.keywords:
                if kw.arg == "file" and isinstance(kw.value, ast.Attribute) and kw.value.attr == "stderr":
                    offenders.append((node.lineno, ast.unparse(node)))
    assert not offenders, f"direct stderr prints remain: {offenders}"
```

- [ ] **Step 2: Run test, confirm failure**

```
uv run pytest tests/ci/test_cli_uses_log_info.py -v
```
Expected: FAIL — multiple offenders listed.

- [ ] **Step 3: Convert each `print(..., file=sys.stderr)` call**

In `src/quodeq/_cli_evaluation.py`, replace:

Line 118: `print("Starting evidence collection (this may take several minutes per dimension)...", file=sys.stderr)`
→ `log_info("Starting evidence collection (this may take several minutes per dimension)...")`

Line 124: `print(f"Failed to write evidence file {out_file}: {exc}", file=sys.stderr)`
→ `log_error(f"Failed to write evidence file {out_file}: {exc}")`

Line 126: `print(f"Evidence written to {out_file}", file=sys.stderr)`
→ `log_info(f"Evidence written to {out_file}")`

Line 128: `print("Starting evaluation (this may take several minutes per dimension)...", file=sys.stderr)`
→ `log_info("Starting evaluation (this may take several minutes per dimension)...")`

Line 130: `print(f"Report path: {evaluation_dir}/", file=sys.stderr)`
→ `log_info(f"Report path: {evaluation_dir}/")`

Line 131: `print(f"Reports written to {evaluation_dir}/", file=sys.stderr)`
→ `log_info(f"Reports written to {evaluation_dir}/")`

Line 135: `print(f"\nError: {exc}", file=sys.stderr)`
→ `log_error(f"{exc}")`

Line 155: `print(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all", file=sys.stderr)`
→ `log_info(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all")`

Line 162: `print("Single-file mode: per-dimension analysis for deeper coverage", file=sys.stderr)`
→ `log_info("Single-file mode: per-dimension analysis for deeper coverage")`

Line 197: `print(f"Report path: {evaluation_dir}", file=sys.stderr)`
→ `log_info(f"Report path: {evaluation_dir}")`

Add imports at the top of `_cli_evaluation.py`:

```python
from quodeq.shared.logging import log_info, log_error
```

(Verify existing imports don't already include these.)

Leave the stdout prints for dimension scores (`print(f"  {dim}: {score}")` on line 133) unchanged — those are intentional machine-readable output for shell piping.

- [ ] **Step 4: Run tests, confirm pass**

```
uv run pytest tests/ci/test_cli_uses_log_info.py -v
uv run pytest tests/ci/ -q
```
Expected: new test passes. Existing CLI tests may have assertions about stderr output — update any that fail by checking `caplog` or the logger stream instead of `capsys.readouterr().err`. If the tests-fix gets large, split into a follow-up commit.

- [ ] **Step 5: Commit**

```
git add src/quodeq/_cli_evaluation.py tests/ci/test_cli_uses_log_info.py
git commit -m "refactor(cli): route stderr progress through log_info for unified log capture"
```

---

## Task 3: Install RunLogHandler in the CLI pipeline

**Files:**
- Modify: `src/quodeq/_cli_evaluation.py` (`_run_pipeline_with_cleanup`, ~line 192-225)
- Test: `tests/ci/test_run_log_integration.py`

- [ ] **Step 1: Write failing test**

```python
# tests/ci/test_run_log_integration.py
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from quodeq.shared.logging import log_info


def test_run_log_captures_log_info_during_pipeline(tmp_path: Path, monkeypatch) -> None:
    """log_info calls between install/uninstall must land in run.log."""
    from quodeq.shared.run_log import RunLogHandler, RunLogWriter

    run_dir = tmp_path / "project" / "run-1"
    run_dir.mkdir(parents=True)

    writer = RunLogWriter(run_dir)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("quodeq")
    logger.addHandler(handler)
    try:
        log_info("line-one")
        log_info("line-two")
    finally:
        logger.removeHandler(handler)
        writer.close()

    contents = (run_dir / "run.log").read_text()
    assert "line-one" in contents
    assert "line-two" in contents
```

Also add a "harness" test that _run_pipeline_with_cleanup installs + removes the handler:

```python
def test_pipeline_installs_and_removes_run_log_handler(tmp_path: Path, monkeypatch) -> None:
    """_run_pipeline_with_cleanup must install RunLogHandler on entry and remove on exit."""
    import quodeq._cli_evaluation as cli
    from quodeq.shared.run_log import RunLogHandler

    logger = logging.getLogger("quodeq")
    initial_handlers = set(id(h) for h in logger.handlers)

    # Stub _execute_pipeline so we exercise only the wrapper's install/remove logic.
    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        evidence_dir = tmp_path / "proj" / "run" / "evidence"
        evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
        evidence_dir.mkdir(parents=True)
        evaluation_dir.mkdir(parents=True)
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()

        # During pipeline, a RunLogHandler must be attached to the quodeq logger.
        attached: list[bool] = []
        original_execute = cli._execute_pipeline
        def _spy(*a, **k):
            attached.append(any(isinstance(h, RunLogHandler) for h in logger.handlers))
            return 0
        with patch.object(cli, "_execute_pipeline", side_effect=_spy):
            cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    assert attached == [True]
    # After exit, no stray RunLogHandler remains.
    assert not any(isinstance(h, RunLogHandler) for h in logger.handlers)
    assert set(id(h) for h in logger.handlers) == initial_handlers
```

- [ ] **Step 2: Run tests, confirm failure**

```
uv run pytest tests/ci/test_run_log_integration.py -v
```
Expected: second test FAILS — `assert attached == [True]` fails because the handler isn't installed yet.

- [ ] **Step 3: Modify `_run_pipeline_with_cleanup`**

Replace the `try:`/`finally:` block (lines 212-225) with:

```python
    config = _build_run_config(args, inputs=inputs, evidence_dir=evidence_dir)

    # Install a per-run log handler so every log_info lands in run.log.
    from quodeq.shared.run_log import RunLogHandler, RunLogWriter
    writer = RunLogWriter(run_dir)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger_root = logging.getLogger("quodeq")
    _logger_root.addHandler(handler)

    try:
        return _execute_pipeline(args, config, evidence_dir, evaluation_dir)
    finally:
        _logger_root.removeHandler(handler)
        writer.close()
        # Clean up .pid file on exit so we don't leave stale PIDs.
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass
        if is_repo_url(args.repo):
            cleanup_cloned_repo(str(inputs.src))
        worktree_dir = getattr(args, "_worktree_dir", None)
        worktree_origin = getattr(args, "_worktree_origin", None)
        if worktree_dir and worktree_origin:
            _cleanup_worktree(worktree_origin, worktree_dir)
```

Add at the top of the file if missing: `import logging`.

- [ ] **Step 4: Run tests, confirm pass**

```
uv run pytest tests/ci/test_run_log_integration.py -v
uv run pytest tests/ci/ -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/_cli_evaluation.py tests/ci/test_run_log_integration.py
git commit -m "feat(cli): install RunLogHandler so every run writes run.log"
```

---

## Task 4: Tee subprocess output to run.log in _consume_stream

**Files:**
- Modify: `src/quodeq/services/jobs.py` (`_consume_stream` ~line 276, plus surrounding code that tracks `run_dir`)
- Test: `tests/services/test_jobs_run_log.py`

The subprocess stream doesn't know its `run_dir` at spawn time — `run_dir` is set by the `report_path` marker (jobs.py:243-249) mid-stream. Strategy: once the marker arrives, open a `RunLogWriter` on that run_dir and tee all subsequent + previously-buffered lines to it.

- [ ] **Step 1: Write failing test**

```python
# tests/services/test_jobs_run_log.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.services.jobs import JobManager
from quodeq.services._job_model import Job, STATUS_RUNNING


def test_consume_stream_tees_to_run_log(tmp_path: Path) -> None:
    """Once the report_path marker arrives, subsequent lines land in run.log."""
    project = "proj-uuid"
    run_id = "run-A"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    jm = JobManager(reports_root=tmp_path)
    job = Job(
        job_id="job-1",
        status=STATUS_RUNNING,
        command=["x"],
        started_at="2026-04-20T00:00:00+00:00",
        ended_at=None,
        exit_code=None,
    )
    jm._store.put(job)  # internal — test helper

    marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})
    stream = iter([
        "pre-marker line\n",
        marker + "\n",
        "post-marker line\n",
    ])
    jm._consume_stream("job-1", stream)

    contents = (run_dir / "run.log").read_text()
    # Both pre-marker (buffered) and post-marker lines must appear, in order.
    assert "pre-marker line" in contents
    assert "post-marker line" in contents
    assert contents.index("pre-marker line") < contents.index("post-marker line")


def test_consume_stream_no_run_dir_silent(tmp_path: Path) -> None:
    """If no report_path marker ever arrives, consume_stream completes without error."""
    jm = JobManager(reports_root=tmp_path)
    job = Job(
        job_id="job-2", status=STATUS_RUNNING, command=["x"],
        started_at="2026-04-20T00:00:00+00:00", ended_at=None, exit_code=None,
    )
    jm._store.put(job)
    jm._consume_stream("job-2", iter(["line-1\n", "line-2\n"]))
    # No run.log anywhere — nothing to assert beyond "did not raise".
```

- [ ] **Step 2: Run test, confirm failure**

```
uv run pytest tests/services/test_jobs_run_log.py -v
```
Expected: FAIL — `run.log` does not exist (teeing not implemented).

- [ ] **Step 3: Modify `_consume_stream`**

Before modifying, identify where the `report_path` marker is parsed. Current code at jobs.py:243-249 sets `job.output_project` and `job.output_run_id`. Introduce a per-job `RunLogWriter` lazily after the marker arrives.

In `src/quodeq/services/jobs.py`, add near the top of the module:
```python
from quodeq.shared.run_log import RunLogWriter
```

Add an instance attribute for writers to `JobManager.__init__` (find the existing `__init__` method):
```python
self._run_log_writers: dict[str, RunLogWriter] = {}
# Buffer of pre-marker lines per job, flushed once run_dir is known.
self._pre_marker_buffer: dict[str, list[str]] = {}
```

Replace `_consume_stream` (line 276-290) with:

```python
    def _consume_stream(self, job_id: str, stream: Iterable[str] | None) -> None:
        if stream is None:
            return
        batch: list[str] = []
        self._pre_marker_buffer.setdefault(job_id, [])
        try:
            for line in stream:
                stripped = line.rstrip("\n")
                batch.append(stripped)
                self._tee_run_log(job_id, stripped)
                if len(batch) >= _CONSUME_BATCH_SIZE:
                    if not self._flush_batch(job_id, batch):
                        return
                    batch.clear()
        except (IOError, BrokenPipeError) as exc:
            _logger.warning("Stream read error for job %s: %s", job_id, exc)
        if batch:
            self._flush_batch(job_id, batch)
        # Close the writer when the stream ends.
        writer = self._run_log_writers.pop(job_id, None)
        if writer is not None:
            writer.close()
        self._pre_marker_buffer.pop(job_id, None)

    def _tee_run_log(self, job_id: str, line: str) -> None:
        """Forward *line* to the job's run.log writer.

        Before the report_path marker arrives, ``run_dir`` is unknown — lines
        are held in ``self._pre_marker_buffer`` and flushed once the marker
        resolves the directory.
        """
        writer = self._run_log_writers.get(job_id)
        if writer is None:
            # Try to resolve run_dir from the job snapshot now.
            job = self._store.get(job_id)
            if job and job.output_project and job.output_run_id and self._reports_root is not None:
                run_dir = self._reports_root / job.output_project / job.output_run_id
                if run_dir.is_dir():
                    writer = RunLogWriter(run_dir)
                    self._run_log_writers[job_id] = writer
                    # Flush any buffered pre-marker lines.
                    for pending in self._pre_marker_buffer.get(job_id, []):
                        writer.write(pending)
                    self._pre_marker_buffer[job_id] = []
            if writer is None:
                self._pre_marker_buffer.setdefault(job_id, []).append(line)
                return
        writer.write(line)
```

Also verify `JobManager.__init__` stores `reports_root` as `self._reports_root`. If it doesn't, add it; the constructor already accepts `reports_root` in current usage (see `cancel_job` which uses `reports_root` — pass it through).

- [ ] **Step 4: Run tests, confirm pass**

```
uv run pytest tests/services/test_jobs_run_log.py tests/services/ -q
```
Expected: both new tests PASS, existing services tests still PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/services/jobs.py tests/services/test_jobs_run_log.py
git commit -m "feat(jobs): tee subprocess output to per-run run.log"
```

---

## Task 5: Plain `/api/jobs/<id>/logs?since=N` endpoint

**Files:**
- Create: `src/quodeq/api/_log_stream_routes.py`
- Test: `tests/api/test_log_stream_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_log_stream_routes.py
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

from quodeq.api._log_stream_routes import register_log_stream_routes


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    app = Flask(__name__)
    app.config["_api_key"] = None  # localhost-only mode, works with test client
    app.config["_reports_dir"] = tmp_path

    # Fake provider that resolves job_id -> run_dir via run_dir mapping.
    class FakeProvider:
        def __init__(self) -> None:
            self.map: dict[str, Path] = {}
        def get_log_run_dir(self, job_id: str) -> Path | None:
            return self.map.get(job_id)
        def is_job_complete(self, job_id: str) -> bool:
            return job_id.endswith("-done")

    provider = FakeProvider()
    app.config["_provider"] = provider
    register_log_stream_routes(app)
    return app


def _seed_run(tmp_path: Path, app: Flask, job_id: str, content: str) -> Path:
    run_dir = tmp_path / job_id
    run_dir.mkdir()
    (run_dir / "run.log").write_text(content)
    app.config["_provider"].map[job_id] = run_dir
    return run_dir


def test_plain_logs_returns_content(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-1-done", "first\nsecond\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-1-done/logs")
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["lines"] == ["first", "second"]
    assert data["nextOffset"] == len("first\nsecond\n")
    assert data["done"] is True


def test_plain_logs_since_offset(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-2", "first\nsecond\nthird\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-2/logs?since=6")  # after "first\n"
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["lines"] == ["second", "third"]


def test_plain_logs_404_when_log_missing(tmp_path, app) -> None:
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    app.config["_provider"].map["job-3"] = run_dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-3/logs")
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_plain_logs_410_when_run_dir_missing(tmp_path, app) -> None:
    app.config["_provider"].map["job-4"] = tmp_path / "gone"  # not a real dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-4/logs")
    assert resp.status_code == HTTPStatus.GONE


def test_plain_logs_partial_line_stripped(tmp_path, app) -> None:
    """If the last line lacks a trailing newline, it's not returned — caller polls again."""
    _seed_run(tmp_path, app, "job-5", "complete\npartial-tail")
    client = app.test_client()
    resp = client.get("/api/jobs/job-5/logs")
    data = resp.get_json()
    assert data["lines"] == ["complete"]
    assert data["nextOffset"] == len("complete\n")
```

- [ ] **Step 2: Run tests, confirm failure**

```
uv run pytest tests/api/test_log_stream_routes.py -v
```
Expected: `ImportError` on `register_log_stream_routes`.

- [ ] **Step 3: Implement plain endpoint**

```python
# src/quodeq/api/_log_stream_routes.py
"""Log-stream routes — SSE live stream + plain JSON fallback for /api/jobs/<id>/logs."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api.security import require_auth


def _resolve_run_log(job_id: str) -> tuple[Path | None, int]:
    """Return (log_path, status_hint). status_hint is 0 on success, HTTP code on error."""
    provider = current_app.config.get("_provider")
    if provider is None or not hasattr(provider, "get_log_run_dir"):
        return None, HTTPStatus.NOT_FOUND
    run_dir = provider.get_log_run_dir(job_id)
    if run_dir is None or not run_dir.is_dir():
        return None, HTTPStatus.GONE
    log_path = run_dir / "run.log"
    if not log_path.exists():
        return None, HTTPStatus.NOT_FOUND
    return log_path, 0


def _read_tail(log_path: Path, since: int) -> tuple[list[str], int]:
    """Read lines starting at byte offset *since*. Returns (lines, next_offset).

    Drops any trailing partial line (without newline); caller polls again.
    """
    with open(log_path, "rb") as fh:
        fh.seek(since)
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    if not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return [], since  # no complete line yet
        text = text[:last_nl + 1]
    consumed = len(text.encode("utf-8"))
    lines = text.splitlines()
    return lines, since + consumed


def register_log_stream_routes(app: Flask) -> None:
    """Register plain + SSE log-stream routes on *app*."""

    @app.get("/api/jobs/<job_id>/logs")
    @require_auth
    def plain_logs(job_id: str) -> Response | tuple[Response, int]:
        log_path, err = _resolve_run_log(job_id)
        if log_path is None:
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        since = max(0, request.args.get("since", 0, type=int))
        lines, next_offset = _read_tail(log_path, since)
        provider = current_app.config.get("_provider")
        done = bool(provider and getattr(provider, "is_job_complete", lambda _: False)(job_id))
        return jsonify({"lines": lines, "nextOffset": next_offset, "done": done})
```

- [ ] **Step 4: Run tests, confirm pass**

```
uv run pytest tests/api/test_log_stream_routes.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/api/_log_stream_routes.py tests/api/test_log_stream_routes.py
git commit -m "feat(api): add plain /api/jobs/<id>/logs endpoint"
```

---

## Task 6: SSE `/api/jobs/<id>/logs/stream` endpoint

**Files:**
- Modify: `src/quodeq/api/_log_stream_routes.py` (add SSE route)
- Modify: `tests/api/test_log_stream_routes.py` (add SSE tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/api/test_log_stream_routes.py`:

```python
def _collect_sse(resp, max_events: int = 50) -> list[dict]:
    """Parse an SSE response body into a list of {id, event, data} dicts."""
    events: list[dict] = []
    current: dict = {}
    for raw in resp.response:  # Flask test-client yields bytes chunks
        chunk = raw.decode("utf-8")
        for line in chunk.splitlines():
            if line.startswith("id:"):
                current["id"] = line[3:].strip()
            elif line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("data:"):
                current["data"] = line[5:].strip()
            elif line == "":
                if current:
                    events.append(current)
                    current = {}
                    if len(events) >= max_events:
                        return events
    if current:
        events.append(current)
    return events


def test_sse_replays_existing_content(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-sse-1-done", "alpha\nbeta\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-sse-1-done/logs/stream")
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type.startswith("text/event-stream")
    events = _collect_sse(resp)
    data_events = [e for e in events if "data" in e]
    assert [e["data"] for e in data_events] == ["alpha", "beta"]
    assert any(e.get("event") == "done" for e in events)


def test_sse_respects_last_event_id(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-sse-2-done", "alpha\nbeta\ngamma\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-sse-2-done/logs/stream",
                      headers={"Last-Event-ID": str(len("alpha\n"))})
    events = _collect_sse(resp)
    data_events = [e for e in events if "data" in e]
    assert [e["data"] for e in data_events] == ["beta", "gamma"]


def test_sse_404_on_missing_log(tmp_path, app) -> None:
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    app.config["_provider"].map["job-sse-3"] = run_dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-sse-3/logs/stream")
    assert resp.status_code == HTTPStatus.NOT_FOUND
```

- [ ] **Step 2: Run tests, confirm failure**

```
uv run pytest tests/api/test_log_stream_routes.py -v -k sse
```
Expected: FAIL — route not yet registered.

- [ ] **Step 3: Extend `_log_stream_routes.py` with SSE**

Append to the module:

```python
import os
import time

_POLL_MS = int(os.environ.get("QUODEQ_LOG_STREAM_POLL_MS", "100"))
_MAX_WAIT_S = int(os.environ.get("QUODEQ_LOG_STREAM_MAX_WAIT_S", "10"))


def _sse_line(data: str, event: str | None = None, event_id: int | None = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}\n")
    if event is not None:
        parts.append(f"event: {event}\n")
    # Escape CR so one log line is one SSE frame.
    parts.append(f"data: {data}\n\n")
    return "".join(parts)


def _sse_generator(log_path: Path, initial_offset: int, is_done):
    """Yield SSE frames by tailing *log_path* starting at *initial_offset*."""
    offset = initial_offset
    waited_ms = 0
    yield ":keepalive\n\n"  # Flask test-client needs at least one byte
    while True:
        if not log_path.exists():
            if waited_ms >= _MAX_WAIT_S * 1000:
                yield _sse_line("log file unavailable", event="error")
                return
            time.sleep(_POLL_MS / 1000)
            waited_ms += _POLL_MS
            continue
        with open(log_path, "rb") as fh:
            fh.seek(offset)
            raw = fh.read()
        text = raw.decode("utf-8", errors="replace")
        if text:
            complete = text if text.endswith("\n") else text[: text.rfind("\n") + 1]
            if complete:
                for line in complete.splitlines():
                    offset += len(line.encode("utf-8")) + 1  # +1 for '\n'
                    yield _sse_line(line, event_id=offset)
        if is_done():
            yield _sse_line("", event="done", event_id=offset)
            return
        time.sleep(_POLL_MS / 1000)


def register_log_stream_routes(app: Flask) -> None:
    """Register plain + SSE log-stream routes on *app*."""

    @app.get("/api/jobs/<job_id>/logs")
    @require_auth
    def plain_logs(job_id: str) -> Response | tuple[Response, int]:
        log_path, err = _resolve_run_log(job_id)
        if log_path is None:
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        since = max(0, request.args.get("since", 0, type=int))
        lines, next_offset = _read_tail(log_path, since)
        provider = current_app.config.get("_provider")
        done = bool(provider and getattr(provider, "is_job_complete", lambda _: False)(job_id))
        return jsonify({"lines": lines, "nextOffset": next_offset, "done": done})

    @app.get("/api/jobs/<job_id>/logs/stream")
    @require_auth
    def stream_logs(job_id: str) -> Response | tuple[Response, int]:
        log_path, err = _resolve_run_log(job_id)
        if log_path is None:
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        last_event_id = request.headers.get("Last-Event-ID", "")
        try:
            initial_offset = int(last_event_id) if last_event_id else 0
        except ValueError:
            initial_offset = 0
        provider = current_app.config.get("_provider")
        is_done = (lambda: bool(provider and getattr(provider, "is_job_complete", lambda _: False)(job_id)))

        resp = Response(
            _sse_generator(log_path, initial_offset, is_done),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
```

Note: replace the earlier `register_log_stream_routes` definition — keep only the combined version shown here.

- [ ] **Step 4: Run tests, confirm pass**

```
uv run pytest tests/api/test_log_stream_routes.py -v
```
Expected: all tests PASS. If SSE tests hang on `test_sse_replays_existing_content`, verify `is_done()` returns True immediately (seeded job_id ends with `-done`), which is the signal for the generator to exit.

- [ ] **Step 5: Commit**

```
git add src/quodeq/api/_log_stream_routes.py tests/api/test_log_stream_routes.py
git commit -m "feat(api): add SSE /api/jobs/<id>/logs/stream endpoint"
```

---

## Task 7: Register new routes + provider method

**Files:**
- Modify: `src/quodeq/api/routes_registry.py`
- Modify: `src/quodeq/services/filesystem.py` (add `get_log_run_dir` and `is_job_complete` to the provider)
- Test: `tests/api/test_log_stream_registered.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_log_stream_registered.py
from quodeq.api.app import create_app


def test_log_stream_routes_registered() -> None:
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/jobs/<job_id>/logs" in rules
    assert "/api/jobs/<job_id>/logs/stream" in rules
```

- [ ] **Step 2: Run test, confirm failure**

```
uv run pytest tests/api/test_log_stream_registered.py -v
```
Expected: FAIL — routes not registered.

- [ ] **Step 3: Add provider methods**

In `src/quodeq/services/filesystem.py`, add to `FilesystemActionProvider`:

```python
    def get_log_run_dir(self, job_id: str) -> Path | None:
        """Return the run_dir for *job_id*, or None if unknown.

        Handles both internal JobManager ids and 'ext-<run_id>' external ids.
        """
        if job_id.startswith("ext-"):
            run_id = job_id[len("ext-"):]
            reports_root = self._reports_dir  # existing accessor
            if reports_root is None or not reports_root.is_dir():
                return None
            for project_dir in reports_root.iterdir():
                candidate = project_dir / run_id
                if candidate.is_dir():
                    return candidate
            return None
        # Internal: delegate to JobManager
        snapshot = self._jobs.get_snapshot(job_id)
        if snapshot is None or snapshot.output_project is None or snapshot.output_run_id is None:
            return None
        if self._reports_dir is None:
            return None
        return self._reports_dir / snapshot.output_project / snapshot.output_run_id

    def is_job_complete(self, job_id: str) -> bool:
        """Return True if *job_id* has reached a terminal state."""
        if job_id.startswith("ext-"):
            run_dir = self.get_log_run_dir(job_id)
            return run_dir is not None and (run_dir / "scan.json").exists()
        snapshot = self._jobs.get_snapshot(job_id)
        return snapshot is not None and snapshot.status in {"done", "failed", "cancelled"}
```

(Verify attribute names `self._reports_dir` and `self._jobs` match the existing class — adjust if they differ.)

- [ ] **Step 4: Register the new routes**

In `src/quodeq/api/routes_registry.py`, add import:
```python
from quodeq.api._log_stream_routes import register_log_stream_routes
```

In `register_all_routes`, add one line after `register_evaluation_item_routes(app, provider)`:
```python
    register_log_stream_routes(app)
```

- [ ] **Step 5: Run tests, confirm pass**

```
uv run pytest tests/api/test_log_stream_registered.py -v
uv run pytest tests/api/ -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/quodeq/api/routes_registry.py src/quodeq/services/filesystem.py tests/api/test_log_stream_registered.py
git commit -m "feat(api): register log-stream routes and provider helpers"
```

---

## Task 8: Add xterm.js UI dependencies

**Files:**
- Modify: `src/quodeq/ui/package.json`

- [ ] **Step 1: Install dependencies**

```
cd src/quodeq/ui
npm install xterm@^5.3.0 xterm-addon-fit@^0.8.0
```

- [ ] **Step 2: Verify entries in package.json**

Confirm `src/quodeq/ui/package.json` `dependencies` now includes:
```json
"xterm": "^5.3.0",
"xterm-addon-fit": "^0.8.0"
```

- [ ] **Step 3: Verify build still works**

```
cd src/quodeq/ui
npm run build
```
Expected: no errors; dist output produced.

- [ ] **Step 4: Commit**

```
git add src/quodeq/ui/package.json src/quodeq/ui/package-lock.json
git commit -m "chore(ui): add xterm and xterm-addon-fit deps"
```

---

## Task 9: LiveTerminal component

**Files:**
- Create: `src/quodeq/ui/src/features/evaluation/components/LiveTerminal.jsx`
- Create: `src/quodeq/ui/src/features/evaluation/components/LiveTerminal.css`
- Test: `src/quodeq/ui/src/features/evaluation/components/LiveTerminal.test.jsx`

- [ ] **Step 1: Write failing test**

```jsx
// src/quodeq/ui/src/features/evaluation/components/LiveTerminal.test.jsx
import { render, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LiveTerminal from './LiveTerminal.jsx';

class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    FakeEventSource.instances.push(this);
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  close() { this.closed = true; }
  _emit(name, data) { this.listeners[name] && this.listeners[name]({ data }); }
}
FakeEventSource.instances = [];

describe('LiveTerminal', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    global.EventSource = FakeEventSource;
  });

  it('mounts and opens an EventSource for the given job', () => {
    render(<LiveTerminal jobId="job-xyz" />);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe('/api/jobs/job-xyz/logs/stream');
  });

  it('closes the EventSource on unmount', () => {
    const { unmount } = render(<LiveTerminal jobId="job-xyz" />);
    const es = FakeEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });

  it('closes the EventSource when a done event fires', () => {
    render(<LiveTerminal jobId="job-xyz" />);
    const es = FakeEventSource.instances[0];
    act(() => { es._emit('done', ''); });
    expect(es.closed).toBe(true);
  });
});
```

- [ ] **Step 2: Run test, confirm failure**

```
cd src/quodeq/ui
npx vitest run src/features/evaluation/components/LiveTerminal.test.jsx
```
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement the component**

```jsx
// src/quodeq/ui/src/features/evaluation/components/LiveTerminal.jsx
import React, { useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import './LiveTerminal.css';

export default function LiveTerminal({ jobId }) {
  const containerRef = useRef(null);
  const termRef = useRef(null);
  const esRef = useRef(null);
  const [open, setOpen] = useState(true);
  const [lineCount, setLineCount] = useState(0);

  useEffect(() => {
    if (!jobId || !containerRef.current) return;

    const term = new Terminal({
      convertEol: true,
      fontFamily: 'ui-monospace, Menlo, monospace',
      fontSize: 12,
      theme: { background: '#0d1117' },
      scrollback: 10000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;

    const es = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/logs/stream`);
    esRef.current = es;

    const onMessage = (ev) => {
      term.writeln(ev.data ?? '');
      setLineCount((n) => n + 1);
    };
    const onDone = () => { es.close(); };
    const onError = () => { /* EventSource auto-reconnects; no-op */ };
    es.addEventListener('message', onMessage);
    es.addEventListener('done', onDone);
    es.addEventListener('error', onError);

    const onResize = () => { try { fit.fit(); } catch { /* ignore */ } };
    window.addEventListener('resize', onResize);

    return () => {
      window.removeEventListener('resize', onResize);
      es.close();
      term.dispose();
      termRef.current = null;
      esRef.current = null;
    };
  }, [jobId]);

  return (
    <div className="live-terminal">
      <button
        type="button"
        className="live-terminal__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? '▾' : '▸'} Terminal ({lineCount} lines)
      </button>
      <div
        ref={containerRef}
        className={`live-terminal__body ${open ? '' : 'live-terminal__body--collapsed'}`}
      />
    </div>
  );
}
```

```css
/* src/quodeq/ui/src/features/evaluation/components/LiveTerminal.css */
.live-terminal {
  margin-top: 12px;
  border-top: 1px solid var(--color-border, #21262d);
  padding-top: 8px;
}
.live-terminal__toggle {
  background: transparent;
  border: none;
  color: var(--color-text-muted, #8b949e);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 0;
}
.live-terminal__body {
  height: 320px;
  margin-top: 8px;
  border-radius: 6px;
  overflow: hidden;
}
.live-terminal__body--collapsed {
  display: none;
}
```

- [ ] **Step 4: Run test, confirm pass**

```
cd src/quodeq/ui
npx vitest run src/features/evaluation/components/LiveTerminal.test.jsx
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/ui/src/features/evaluation/components/LiveTerminal.{jsx,css,test.jsx}
git commit -m "feat(ui): add LiveTerminal component backed by EventSource + xterm.js"
```

---

## Task 10: Embed LiveTerminal in EvaluationStatus

**Files:**
- Modify: `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx`

- [ ] **Step 1: Update the render tree**

In `EvaluationStatus.jsx`, add the import at the top:
```jsx
import LiveTerminal from './LiveTerminal.jsx';
```

Modify the `EvaluationStatus` component's return (current line 180-187) to:

```jsx
  return (
    <div className="panel evaluate-job-panel">
      <JobHeader job={job} onDismiss={onDismiss} onCancel={onCancel} />
      <JobMeta job={job} projectName={deriveProjectName(job.repo)} />
      <ConsolePanel job={job} consoleOpen={consoleOpen} setConsoleOpen={setConsoleOpen} logViewerRef={logViewerRef} hasEvaluations={hasEvaluations} />
      {job.jobId ? <LiveTerminal jobId={job.jobId} /> : null}
      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
```

- [ ] **Step 2: Manual smoke test**

```
cd src/quodeq/ui
npm run dev
```
Open dashboard, start any evaluation. Expected: the existing status card still renders; a new collapsible "Terminal (N lines)" pane appears below with live stderr lines streaming in. Collapse/expand works. Works for CLI-started runs too (`ext-` prefix).

- [ ] **Step 3: Commit**

```
git add src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx
git commit -m "feat(ui): embed LiveTerminal in EvaluationStatus"
```

---

## Task 11: End-to-end smoke test

**Files:**
- Create: `tests/ci/test_terminal_stream_e2e.py`

- [ ] **Step 1: Write the test**

```python
# tests/ci/test_terminal_stream_e2e.py
"""End-to-end: run a tiny CLI evaluation, verify run.log is written."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_cli_writes_run_log(tmp_path: Path) -> None:
    # Seed a minimal project.
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    env = {**os.environ,
           "QUODEQ_REPORTS_DIR": str(reports),
           "QUODEQ_DRY_RUN": "1"}  # dry-run keeps the test fast and offline
    proc = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "evaluate", str(src),
         "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"

    # Find the single run_dir.
    project_dirs = [d for d in reports.iterdir() if d.is_dir()]
    assert len(project_dirs) == 1, project_dirs
    run_dirs = [d for d in project_dirs[0].iterdir() if d.is_dir()]
    assert len(run_dirs) == 1, run_dirs
    run_dir = run_dirs[0]

    log_path = run_dir / "run.log"
    assert log_path.exists(), f"run.log missing in {run_dir}"
    contents = log_path.read_text()
    # A dry-run still emits the "Starting evaluation..." banner via log_info.
    assert "Starting evaluation" in contents or "Dimensions:" in contents
```

- [ ] **Step 2: Run test, confirm pass**

```
uv run pytest tests/ci/test_terminal_stream_e2e.py -v
```
Expected: PASS. If the CLI's `--dry-run` flag differs (verify in `_cli_evaluation.py`), adjust args. If dry-run isn't supported, the test can point at a single-file analysis mode — keep the test bounded to <60s.

- [ ] **Step 3: Final verification — full test suite**

```
uv run pytest -q
```
Expected: all tests PASS, no regressions.

- [ ] **Step 4: Commit**

```
git add tests/ci/test_terminal_stream_e2e.py
git commit -m "test(ci): add end-to-end run.log smoke test"
```

---

## Post-Implementation Verification

Manual check after all tasks:

1. Start dashboard: `quodeq dashboard`.
2. Start an evaluation from the dashboard UI → terminal pane appears, streams live.
3. In a second terminal, `quodeq evaluate .` in any repo → open dashboard → the external run shows up in the evaluation tab → terminal pane streams live (not "inferred from filesystem").
4. Reload the dashboard mid-run → terminal replays from the first line, then resumes tailing.
5. Open a completed historical run → terminal shows the full recorded output.
6. Disconnect wifi briefly mid-run → EventSource reconnects automatically; no duplicate lines, no gaps.

## Rollback

Each task is a standalone commit; revert in reverse order if needed. The producer changes (Tasks 2-4) are additive — removing them doesn't break existing flows. The UI change (Task 10) is a single-line removal.
