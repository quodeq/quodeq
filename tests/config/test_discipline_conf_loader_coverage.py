"""Tests for config._discipline_conf_loader — INI-style discipline file loading."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.config._discipline_conf_loader import load_disciplines_from_file
from quodeq.config._discipline_rule import DisciplineRule


class TestLoadDisciplinesFromFile:
    def test_basic_loading(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[python]\n"
            "language = python\n"
            "category = backend\n"
            "detect_file = requirements.txt\n"
            "detect_priority = 10\n"
        )
        rules = load_disciplines_from_file(conf)
        assert "python" in rules
        rule = rules["python"]
        assert isinstance(rule, DisciplineRule)
        assert rule.name == "python"
        assert rule.language == "python"
        assert rule.category == "backend"
        assert rule.detect_priority == 10
        assert "requirements.txt" in rule.detect_files

    def test_multiple_sections(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[python]\n"
            "language = python\n"
            "\n"
            "[typescript]\n"
            "language = typescript\n"
            "detect_file = package.json\n"
            "detect_contains = \"typescript\"\n"
        )
        rules = load_disciplines_from_file(conf)
        assert len(rules) == 2
        assert "python" in rules
        assert "typescript" in rules
        assert "typescript" in rules["typescript"].detect_contains

    def test_comments_and_blank_lines_ignored(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "# This is a comment\n"
            "\n"
            "[python]\n"
            "# another comment\n"
            "language = python\n"
            "\n"
        )
        rules = load_disciplines_from_file(conf)
        assert "python" in rules

    def test_lines_before_section_ignored(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "orphan_key = orphan_value\n"
            "[python]\n"
            "language = python\n"
        )
        rules = load_disciplines_from_file(conf)
        assert "python" in rules
        assert rules["python"].language == "python"

    def test_missing_file_raises_value_error(self, tmp_path):
        missing = tmp_path / "nonexistent.conf"
        with pytest.raises(ValueError, match="Cannot read"):
            load_disciplines_from_file(missing)

    def test_detect_fallback(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[generic]\n"
            "language = generic\n"
            "detect_fallback = true\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["generic"].detect_fallback is True

    def test_detect_excludes_csv(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[python]\n"
            "language = python\n"
            "detect_excludes = node_modules, .git, __pycache__\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["python"].detect_excludes == ("node_modules", ".git", "__pycache__")

    def test_suggested_topics_csv(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[python]\n"
            "language = python\n"
            "suggested_topics = security, reliability, performance\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["python"].suggested_topics == ("security", "reliability", "performance")

    def test_detect_glob_and_dir(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[react]\n"
            "language = javascript\n"
            "detect_glob = src/**/*.jsx\n"
            "detect_dir = src/components\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["react"].detect_glob == "src/**/*.jsx"
        assert rules["react"].detect_dir == "src/components"

    def test_detect_requires_file(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[django]\n"
            "language = python\n"
            "detect_requires_file = manage.py\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["django"].detect_requires_file == "manage.py"

    def test_multiple_detect_files(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[node]\n"
            "language = javascript\n"
            "detect_file = package.json\n"
            "detect_file_alt = yarn.lock\n"
            "detect_file_alt2 = pnpm-lock.yaml\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["node"].detect_files == ("package.json", "yarn.lock", "pnpm-lock.yaml")

    def test_empty_file(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text("")
        rules = load_disciplines_from_file(conf)
        assert rules == {}

    def test_line_without_equals_ignored(self, tmp_path):
        conf = tmp_path / "disciplines.conf"
        conf.write_text(
            "[python]\n"
            "language = python\n"
            "this line has no equals sign\n"
        )
        rules = load_disciplines_from_file(conf)
        assert rules["python"].language == "python"
