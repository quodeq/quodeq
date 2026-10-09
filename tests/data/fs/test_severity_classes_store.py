from __future__ import annotations

import json
import os
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


def test_unchanged_standards_are_read_once_and_a_touched_one_is_read_again(tmp_path: Path, monkeypatch) -> None:
    from quodeq.data.fs import compiled_standards

    compiled = tmp_path / "compiled"
    _write(compiled / "a.json", {"principles": [{"requirements": [{"id": "A-1", "severity": "major"}]}]})
    _write(compiled / "b.json", {"principles": [{"requirements": [{"id": "B-1", "severity": "minor"}]}]})
    reads: list[str] = []
    real = compiled_standards.iter_compiled_standards

    def counting(directory: Path):
        for stem, data in real(directory):
            reads.append(stem)
            yield stem, data

    monkeypatch.setattr(compiled_standards, "iter_compiled_standards", counting)
    dirs = lambda: (compiled, None)  # noqa: E731
    first = load_severity_classes(None, standard_dirs_fn=dirs)
    assert load_severity_classes(None, standard_dirs_fn=dirs) == first == {"A-1": "major", "B-1": "minor"}
    assert sorted(reads) == ["a", "b"]

    _write(compiled / "a.json", {"principles": [{"requirements": [{"id": "A-1", "severity": "critical"}, {"id": "A-2", "severity": "major"}]}]})
    os.utime(compiled / "a.json", ns=(1, 1))
    assert load_severity_classes(None, standard_dirs_fn=dirs) == {"A-1": "critical", "A-2": "major", "B-1": "minor"}
    assert sorted(reads) == ["a", "a", "b", "b"]


def test_a_changed_overrides_file_is_picked_up(tmp_path: Path) -> None:
    compiled = tmp_path / "compiled"
    _write(compiled / "s.json", {"principles": [{"requirements": [{"id": "S-1", "severity": "major"}]}]})
    repo = tmp_path / "repo"
    overrides = repo / ".quodeq" / "standards-overrides.json"
    dirs = lambda: (compiled, None)  # noqa: E731
    assert load_severity_classes(repo, standard_dirs_fn=dirs) == {"S-1": "major"}
    _write(overrides, {"version": 1, "overrides": {"S-1": {"severity": "minor"}}})
    assert load_severity_classes(repo, standard_dirs_fn=dirs) == {"S-1": "minor"}
    overrides.unlink()
    assert load_severity_classes(repo, standard_dirs_fn=dirs) == {"S-1": "major"}


def test_an_online_location_has_no_repo_root(tmp_path: Path, monkeypatch) -> None:
    compiled = tmp_path / "compiled"
    _write(compiled / "s.json", {"principles": [{"requirements": [{"id": "S-1", "severity": "major"}]}]})
    repo = tmp_path / "repo"
    _write(repo / ".quodeq" / "standards-overrides.json", {"version": 1, "overrides": {"S-1": {"severity": "minor"}}})
    project = tmp_path / "reports" / "proj"
    _write(project / "repository_info.json", {"path": str(repo), "location": "online"})
    run = project / "run1"
    run.mkdir()
    monkeypatch.setattr("quodeq.data.fs.severity_classes_store._standard_dirs", lambda: (compiled, None))
    assert load_severity_classes_for_run(run) == {"S-1": "major"}
