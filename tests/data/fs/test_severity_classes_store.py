from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.severity_classes_store import load_severity_classes, load_severity_classes_for_run
from quodeq.data.fs.standards_loader import read_severity_classes


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_read_merges_compiled_and_custom_and_skips_junk(tmp_path: Path) -> None:
    compiled = tmp_path / "compiled"
    custom = tmp_path / "evaluators"
    _write(compiled / "security.json", {"principles": [{"requirements": [{"id": "S-INT-2", "severity": "critical"}, {"id": "S-X", "severity": "blocker"}]}]})
    _write(custom / "house.json", {"principles": [{"requirements": [{"id": "H-1", "severity": "major"}, {"id": "S-INT-2", "severity": "major"}]}]})
    (compiled / "broken.json").write_text("{not json", encoding="utf-8")
    assert read_severity_classes(compiled, custom) == {"S-INT-2": "major", "H-1": "major"}
    assert read_severity_classes(None, None) == {}
    assert read_severity_classes(tmp_path / "missing", None) == {}


def test_load_applies_the_project_override(tmp_path: Path) -> None:
    compiled = tmp_path / "compiled"
    _write(compiled / "security.json", {"principles": [{"requirements": [{"id": "S-AUT-3", "severity": "major"}]}]})
    repo = tmp_path / "repo"
    _write(repo / ".quodeq" / "standards-overrides.json", {"version": 1, "overrides": {"S-AUT-3": {"severity": "minor"}}})
    out = load_severity_classes(repo, standard_dirs_fn=lambda: (compiled, None))
    assert out == {"S-AUT-3": "minor"}
    assert load_severity_classes(None, standard_dirs_fn=lambda: (compiled, None)) == {"S-AUT-3": "major"}


def test_load_for_run_resolves_the_repo_from_repository_info(tmp_path: Path, monkeypatch) -> None:
    compiled = tmp_path / "compiled"
    _write(compiled / "security.json", {"principles": [{"requirements": [{"id": "S-1", "severity": "major"}]}]})
    repo = tmp_path / "repo"
    _write(repo / ".quodeq" / "standards-overrides.json", {"version": 1, "overrides": {"S-1": {"severity": "critical"}}})
    project = tmp_path / "reports" / "proj"
    _write(project / "repository_info.json", {"path": str(repo)})
    run = project / "run1"
    run.mkdir()
    monkeypatch.setattr("quodeq.data.fs.severity_classes_store._standard_dirs", lambda: (compiled, None))
    assert load_severity_classes_for_run(run) == {"S-1": "critical"}
    _write(project / "repository_info.json", {"path": "https://github.com/x/y"})
    assert load_severity_classes_for_run(run) == {"S-1": "major"}
