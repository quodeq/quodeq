"""Tests for build_repository_info's URL-name extraction."""
from __future__ import annotations

from quodeq.data.fs.report_parser._repository import build_repository_info


class TestBuildRepositoryInfo:
    def test_url_name(self):
        info = build_repository_info("https://github.com/org/repo.git", "python")
        assert info["name"] == "repo"
        assert info["location"] == "online"

    def test_url_with_trailing_slash(self):
        # A trailing slash used to leave split("/")[-1] == "", collapsing
        # the repo name to "".
        info = build_repository_info("https://github.com/org/repo/", "python")
        assert info["name"] == "repo"

    def test_url_with_trailing_slash_and_git_suffix(self):
        info = build_repository_info("https://github.com/org/repo.git/", "python")
        assert info["name"] == "repo"

    def test_local_path(self, tmp_path):
        info = build_repository_info(str(tmp_path), None)
        assert info["name"] == tmp_path.name
        assert info["location"] == "local"
