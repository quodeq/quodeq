"""Unit tests for the two phase helpers behind ``resolve_dimension_eval``.

``_suppression_keys`` reads the project's dismissed/deleted state;
``_resolve_from_source`` owns the JSON -> markdown -> evidence fallback chain.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.violation_context import ViolationContext
from quodeq.services.violations import (
    _ResolveOptions,
    _resolve_from_source,
    _suppression_keys,
)


def _ctx() -> ViolationContext:
    return ViolationContext(project="proj", run_id="run", dimension="testdim")


def test_suppression_keys_reads_project_dismissed_and_deleted(tmp_path: Path) -> None:
    """Keys come from the project dir (``base.parent``), not the run dir."""
    project_dir = tmp_path / "project"
    base = project_dir / "run"
    base.mkdir(parents=True)
    (project_dir / "deleted.json").write_text(json.dumps([
        {"dimension": "testdim", "principle": "Clear Naming", "file": "src/app.py"},
    ]))

    keys = _suppression_keys(base)

    assert keys.deleted == {("testdim", "Clear Naming", "src/app.py")}
    assert keys.dismissed.entries == ()


def test_suppression_keys_empty_when_project_has_no_state(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base = project_dir / "run"
    base.mkdir(parents=True)

    keys = _suppression_keys(base)

    assert not keys.deleted


def test_resolve_from_source_prefers_json_eval(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base = project_dir / "run"
    (base / "evaluation").mkdir(parents=True)
    (base / "evaluation" / "testdim.json").write_text(json.dumps({
        "dimension": "testdim", "principles": [], "violations": [],
    }))
    (base / "evaluation" / "testdim_eval.md").write_text("# markdown fallback")

    result = _resolve_from_source(base, _ctx(), _ResolveOptions(), _suppression_keys(base))

    assert isinstance(result, dict)
    assert result["dimension"] == "testdim"


def test_resolve_from_source_falls_back_to_markdown(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base = project_dir / "run"
    (base / "evaluation").mkdir(parents=True)
    markdown = "# Testdim Evaluation\n\n**Overall Score**: 8.0/10\n"
    (base / "evaluation" / "testdim_eval.md").write_text(markdown)

    result = _resolve_from_source(base, _ctx(), _ResolveOptions(), _suppression_keys(base))

    assert result is not None
    assert result["dimension"] == "testdim"
    assert result["runId"] == "run"
    assert result["project"] == "proj"
    # The markdown fallback must actually have parsed *this* file's content,
    # not merely returned a non-None placeholder.
    assert result["rawContent"] == markdown


def test_resolve_from_source_returns_none_when_nothing_exists(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base = project_dir / "run"
    base.mkdir(parents=True)

    assert _resolve_from_source(
        base, _ctx(), _ResolveOptions(), _suppression_keys(base),
    ) is None
