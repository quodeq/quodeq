"""Unit tests for the phase helpers behind ``FsEvaluationMixin.start_evaluation``.

``_resolve_repo_target`` owns the input validation, ``_register_target_project``
the registration + onboarding stamp, ``_git_root_cwd`` the working-directory
choice, and ``_launch_evaluation_job`` the dispatch.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services.base import EvaluationOptions
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from tests.services._evaluation_fixtures import _make_mixin


class TestResolveRepoTarget:
    def test_rejects_a_url_repo(self):
        with pytest.raises(ValueError, match="URL repos are not supported"):
            FsEvaluationMixin._resolve_repo_target("https://github.com/acme/repo.git")

    def test_rejects_a_missing_path(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Repository not found"):
            FsEvaluationMixin._resolve_repo_target(str(tmp_path / "nope"))

    def test_returns_the_resolved_path(self, tmp_path: Path):
        repo = tmp_path / "myrepo"
        repo.mkdir()

        assert FsEvaluationMixin._resolve_repo_target(str(repo)) == repo.resolve()


class TestRegisterTargetProject:
    def test_registers_and_stamps_onboarding(self, tmp_path: Path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()

        FsEvaluationMixin._register_target_project(str(repo), str(reports), EvaluationOptions())

        (info,) = list(reports.glob("*/repository_info.json"))
        assert isinstance(json.loads(info.read_text())["onboardingCompletedAt"], str)


class TestGitRootCwd:
    def test_directory_target_is_its_own_cwd(self, tmp_path: Path):
        repo = tmp_path / "myrepo"
        repo.mkdir()

        assert FsEvaluationMixin._git_root_cwd(repo) == str(repo)

    def test_file_target_walks_up_to_the_git_root(self, tmp_path: Path):
        repo = tmp_path / "myrepo"
        (repo / ".git").mkdir(parents=True)
        nested = repo / "src" / "pkg"
        nested.mkdir(parents=True)
        target = nested / "mod.py"
        target.write_text("x = 1\n")

        assert FsEvaluationMixin._git_root_cwd(target) == str(repo)

    def test_file_target_without_a_git_root_uses_its_parent(self, tmp_path: Path):
        target = tmp_path / "loose.py"
        target.write_text("x = 1\n")

        assert FsEvaluationMixin._git_root_cwd(target) == str(tmp_path)


class TestLaunchEvaluationJob:
    def test_dispatches_the_command_and_returns_the_snapshot(self, tmp_path: Path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        mixin = _make_mixin()

        snapshot = mixin._launch_evaluation_job(
            ["quodeq", "evaluate"], str(tmp_path / "reports"), EvaluationOptions(), repo,
        )

        assert snapshot == {"id": "fake-job"}
        assert mixin._dispatcher.calls == [["quodeq", "evaluate"]]
