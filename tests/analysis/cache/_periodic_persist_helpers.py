"""Config builder shared by the test_periodic_persist* siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.run_types import AnalysisOptions, RunConfig
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="t", language="python", source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _setup(tmp_path: Path, contents: dict[str, str]) -> RunConfig:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for n, t in contents.items():
        (src / n).write_text(t)
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=tmp_path / "work",
        options=AnalysisOptions(subagent_model="test-model"),
        manifest=_make_manifest(sorted(contents.keys())),
    )
