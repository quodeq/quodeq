"""Config and repo builders shared by the test_api_size_cap_dispatch* siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.run_types import AnalysisOptions, RunConfig
from quodeq.analysis.dispatch_policy import DispatchPolicy
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest

CAP = 200  # small test cap, applied via QUODEQ_MAX_API_FILE_SIZE
_TEST_PROVIDER = "test-provider"


def _make_config(
    src: Path, file_names: list[str], *, dispatch: DispatchPolicy | None = None,
) -> RunConfig:
    target = AnalysisTarget(
        name="t", language="python", source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    manifest = SourceManifest(targets=[target], total_files=len(file_names))
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=src, manifest=manifest,
        options=AnalysisOptions(subagent_model="test-model", incremental=False),
        dispatch=dispatch,
    )


def _write_repo(src: Path) -> None:
    """One dispatchable file, one over the cap."""
    src.mkdir(parents=True, exist_ok=True)
    (src / "small.py").write_text("# small\n")
    (src / "big.py").write_text("# big\n" + "x = 1\n" * CAP)
