"""RunConfig builder shared by the test_cache_writer* siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._types import AnalysisOptions, RunConfig


def _make_config(
    src: Path,
    *,
    work_dir: Path | None = None,
    standards_dir: Path | None = None,
    model: str = "sonnet",
    language: str = "kotlin",
) -> RunConfig:
    opts = AnalysisOptions(subagent_model=model)
    return RunConfig(
        src=src,
        language=language,
        standards_dir=standards_dir,
        work_dir=work_dir or src,
        options=opts,
    )
