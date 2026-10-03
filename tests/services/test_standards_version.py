"""The standards fingerprint and its place in the score-cache version hashes."""
from __future__ import annotations

import json
import os
from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import (
    VersionInputs,
    run_scoped_version,
    score_cache_version,
    suppression_state_fingerprint,
)
from quodeq.services.standards_version import standards_fingerprint


def _bump_mtime(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))


def _project(tmp_path: Path, repo: Path | None = None) -> Path:
    reports_root = tmp_path / "reports"
    project_dir = reports_root / "proj"
    project_dir.mkdir(parents=True)
    if repo is not None:
        repo.mkdir(parents=True, exist_ok=True)
        (project_dir / "repository_info.json").write_text(
            json.dumps({"path": str(repo)}), encoding="utf-8")
    return project_dir


def _compiled(tmp_path: Path) -> Path:
    compiled = tmp_path / "standards" / "compiled"
    compiled.mkdir(parents=True)
    (compiled / "security.json").write_text("{}", encoding="utf-8")
    (compiled / "quality.json").write_text("{}", encoding="utf-8")
    return compiled


class TestStandardsFingerprint:
    def test_stable_across_calls(self, tmp_path):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path)
        a = standards_fingerprint(project_dir, compiled_dir=compiled)
        b = standards_fingerprint(project_dir, compiled_dir=compiled)
        assert a == b

    def test_edited_compiled_standard_changes_it(self, tmp_path):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path)
        before = standards_fingerprint(project_dir, compiled_dir=compiled)
        (compiled / "security.json").write_text('{"principles": []}', encoding="utf-8")
        _bump_mtime(compiled / "security.json")
        assert standards_fingerprint(project_dir, compiled_dir=compiled) != before

    def test_added_compiled_standard_changes_it(self, tmp_path):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path)
        before = standards_fingerprint(project_dir, compiled_dir=compiled)
        (compiled / "custom.json").write_text("{}", encoding="utf-8")
        assert standards_fingerprint(project_dir, compiled_dir=compiled) != before

    def test_project_overrides_change_it(self, tmp_path):
        compiled = _compiled(tmp_path)
        repo = tmp_path / "repo"
        project_dir = _project(tmp_path, repo)
        before = standards_fingerprint(project_dir, compiled_dir=compiled)
        (repo / ".quodeq").mkdir()
        (repo / ".quodeq" / "standards-overrides.json").write_text(
            json.dumps({"overrides": {"R1": {"max": 3}}}), encoding="utf-8")
        assert standards_fingerprint(project_dir, compiled_dir=compiled) != before

    def test_other_projects_overrides_do_not_change_it(self, tmp_path):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path, tmp_path / "repo")
        other = tmp_path / "other"
        (other / ".quodeq").mkdir(parents=True)
        before = standards_fingerprint(project_dir, compiled_dir=compiled)
        (other / ".quodeq" / "standards-overrides.json").write_text("{}", encoding="utf-8")
        assert standards_fingerprint(project_dir, compiled_dir=compiled) == before

    def test_missing_compiled_dir_is_tolerated(self, tmp_path):
        project_dir = _project(tmp_path)
        fp = standards_fingerprint(project_dir, compiled_dir=tmp_path / "nowhere")
        assert isinstance(fp, str) and fp

    def test_no_local_repo_is_tolerated(self, tmp_path):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path)
        (project_dir / "repository_info.json").write_text(
            json.dumps({"path": "https://example.invalid/x.git"}), encoding="utf-8")
        assert standards_fingerprint(project_dir, compiled_dir=compiled)


class TestVersionHashesFoldStandards:
    def test_run_scoped_version_changes_with_standards(self):
        a = run_scoped_version(DEFAULT_PARAMS, set(), set(), set(), set(), standards="s1")
        b = run_scoped_version(DEFAULT_PARAMS, set(), set(), set(), set(), standards="s2")
        assert a != b

    def test_memo_fingerprint_changes_with_standards(self):
        a = suppression_state_fingerprint(DEFAULT_PARAMS, set(), set(), standards="s1")
        b = suppression_state_fingerprint(DEFAULT_PARAMS, set(), set(), standards="s2")
        assert a != b

    def test_version_inputs_read_the_project_standards(self, tmp_path, monkeypatch):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path)
        monkeypatch.setattr(
            "quodeq.services.standards_version.standard_dirs", lambda: (compiled, None))
        before = VersionInputs.of(DEFAULT_PARAMS, set(), set(), project_dir)
        _bump_mtime(compiled / "security.json")
        after = VersionInputs.of(DEFAULT_PARAMS, set(), set(), project_dir)
        assert before.standards != after.standards
        assert before.fingerprint != after.fingerprint

    def test_score_cache_version_changes_with_standards(self, tmp_path, monkeypatch):
        compiled = _compiled(tmp_path)
        project_dir = _project(tmp_path)
        monkeypatch.setattr(
            "quodeq.services.standards_version.standard_dirs", lambda: (compiled, None))
        before = score_cache_version(project_dir, DEFAULT_PARAMS)
        _bump_mtime(compiled / "security.json")
        assert score_cache_version(project_dir, DEFAULT_PARAMS) != before
