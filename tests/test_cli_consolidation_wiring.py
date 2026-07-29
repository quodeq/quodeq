"""run_evaluate must consolidate this run's cache entries after it ends.

The flip runs OUTSIDE RunLifecycleContext, alongside the fail-soft SARIF
export, so a failure in it can never turn a completed run into a failed one.
It is skipped for the modes that produce no scored reports, because nothing
of theirs reaches the Overview.

The seam is patched at the three boundaries run_evaluate calls out through,
so no real pipeline, AI provider, or repo is involved.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from quodeq import _cli_evaluation
from quodeq._cli_resolution import ResolvedInputs
from quodeq.analysis.manifest_models import SourceManifest


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    """The attribute set run_evaluate reads before reaching the tail.

    dry_run=True skips check_evaluate_prereqs, so no AI provider is needed.
    """
    defaults = dict(
        repo=str(tmp_path / "src"),
        output=str(tmp_path / "reports"),
        legacy_incremental=False,
        clean_scan=False,
        diff_from=None,
        dry_run=True,
        sarif=None,
        evidence_only=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def wired(tmp_path: Path, monkeypatch):
    """Patch run_evaluate's three outward calls; record consolidation calls."""
    src = tmp_path / "src"
    src.mkdir()
    evaluation_dir = tmp_path / "reports" / "proj" / "run1" / "evaluation"
    evaluation_dir.mkdir(parents=True)
    evidence_dir = evaluation_dir.parent / "evidence"
    evidence_dir.mkdir()
    paths = (tmp_path / "reports", evidence_dir, evaluation_dir)

    monkeypatch.setattr(
        _cli_evaluation, "_resolve_evaluation_inputs",
        lambda a: ResolvedInputs(
            src=src, language="python",
            manifest=SourceManifest(), dims_data={"applies": []},
        ),
    )
    monkeypatch.setattr(_cli_evaluation, "_setup_run_dirs", lambda a, s: paths)
    monkeypatch.setattr(
        _cli_evaluation, "_run_pipeline_with_cleanup", lambda a, i, p: 0,
    )

    calls: list[Path] = []
    # run_evaluate imports this locally, so it resolves at call time and
    # patching the source module is enough.
    monkeypatch.setattr(
        "quodeq.analysis.cache.consolidation.mark_run_consolidated",
        lambda run_dir, cache=None: calls.append(run_dir),
    )
    return calls, evaluation_dir.parent


def test_run_evaluate_consolidates_the_run_dir(tmp_path: Path, wired):
    calls, run_dir = wired
    assert _cli_evaluation.run_evaluate(_args(tmp_path)) == 0
    assert calls == [run_dir]


def test_run_evaluate_skips_consolidation_for_evidence_only(tmp_path: Path, wired):
    """--evidence-only produces no scored reports, so nothing reaches the
    Overview and its entries must stay unconsolidated."""
    calls, _run_dir = wired
    assert _cli_evaluation.run_evaluate(_args(tmp_path, evidence_only=True)) == 0
    assert calls == []


def test_run_evaluate_skips_consolidation_for_diff_from(tmp_path: Path, wired, monkeypatch):
    """--diff-from is evidence-only output for a specific ref. Same reason."""
    calls, _run_dir = wired
    monkeypatch.setattr(
        _cli_evaluation, "resolve_diff_files", lambda src, ref: {"changed.py"},
    )
    assert _cli_evaluation.run_evaluate(_args(tmp_path, diff_from="main")) == 0
    assert calls == []
