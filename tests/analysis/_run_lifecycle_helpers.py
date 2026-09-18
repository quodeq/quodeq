"""Context builder shared by the test_run_lifecycle* siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.run_lifecycle import RunLifecycleContext


def _ctx(tmp_path: Path) -> RunLifecycleContext:
    return RunLifecycleContext(
        run_dir=tmp_path,
        job_id="ext-test",
        dimensions=["security"],
    )
