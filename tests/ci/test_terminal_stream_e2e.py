# tests/ci/test_terminal_stream_e2e.py
"""End-to-end: run a tiny CLI evaluation, verify run.log is written."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.timeout(180)


@pytest.mark.integration
def test_cli_writes_run_log(tmp_path: Path) -> None:
    # Seed a minimal project.
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    env = {**os.environ,
           "QUODEQ_EVALUATIONS_DIR": str(reports),
           "QUODEQ_DRY_RUN": "1"}  # dry-run keeps the test fast and offline
    proc = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "evaluate", str(src),
         "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"CLI failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

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
